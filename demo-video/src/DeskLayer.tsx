import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ASKED, LEAVES, OPENS, onDesk } from "./Beat";
import * as Cal from "./shots/Calendar";
import { C } from "./theme";
import { EASE, EASE_IN_OUT, shot, tween, type ShotId } from "./timing";
import { AT, BUTTON, Desk, type Box, type Piece } from "./ui/Desk";
import { settle } from "./ui/motion";

/**
 * The app's Home, behind the whole of the film from shot 2 to shot 9. It builds itself
 * in shot 2; it stands, dimmed, under every question, with the one card that answers the
 * question lit and lifted; and in shot 9 it steps aside for the phone and its pieces go
 * across to the phone's screen one at a time. It runs on the film's own clock.
 */

const meet = shot("meet").from;
const both = shot("both").from;
const close = shot("close").from;

/** When the mark has landed as the logo. The sidebar is in a little before. */
export const LANDED = meet + 56;
const SIDE = meet + 44;
/** The cards' placeholders start this long after the sidebar, and follow each other. */
const AFTER = 6;
const first = SIDE + AFTER;
/** How long a placeholder stands before its content arrives. */
const WAIT = 14;
const CARDS = [
  "worth",
  "todo",
  "btc",
  "gold",
  "stock",
  "coming",
  "signals",
] as const;
/** When a card's placeholder arrives, and when its content does. */
const card = (piece: (typeof CARDS)[number]): readonly [number, number] => {
  const at = first + CARDS.indexOf(piece) * 3;
  return [at, at + WAIT];
};
/** When each piece's placeholder arrives, and when its content does. */
const ARRIVES: Readonly<Record<Piece, readonly [number, number]>> = {
  side: [SIDE, SIDE],
  title: [first, first],
  note: [first + 2, first + 2],
  markets: [first + 6, first + 6],
  worth: card("worth"),
  todo: card("todo"),
  btc: card("btc"),
  gold: card("gold"),
  stock: card("stock"),
  coming: card("coming"),
  signals: card("signals"),
};
/** When the cards' content starts to move: the price ticks, the lines draw. */
export const ALIVE = first + WAIT + 2;
/** When each placeholder resolves, for the sound. */
export const RESOLVES = CARDS.map((piece) => ARRIVES[piece][1]);

/** The card of Home that answers each question, and how round its corners are. */
export const TARGET: Readonly<Partial<Record<ShotId, Box>>> = {
  why: AT.btc,
  level: BUTTON.check,
  range: AT.btc,
  risk: BUTTON.risk,
  plan: AT.todo,
  calendar: AT.coming,
};
const QUESTIONS = Object.keys(TARGET) as ShotId[];
const opens = (id: ShotId): number => (id === "calendar" ? Cal.ASKED : ASKED);
/** When the dimming opens over the card, and when the card lifts, after its question. */
const SPOT = (id: ShotId): number => (id === "calendar" ? 1 : 3);
const LIFT = (id: ShotId): number => SPOT(id) + 6;

/** When each card lifts and when it opens, in film frames, for the sound. */
export const LIFTS = QUESTIONS.map((id) => shot(id).from + LIFT(id));
export const OPENINGS = QUESTIONS.map((id) => shot(id).from + opens(id));

// Shot 9. The phone comes in first; Home steps to the left to give it room; the sidebar
// becomes the capsule of places; then each card goes across, one after another.

/** The phone's screen in the frame (shots/Both puts the phone there). */
export const SCREEN: Box = { x: 1424, y: 160, w: 352, h: 762 };
/** Home, stepped aside: how large it is drawn and where its corner is. */
const ASIDE = { k: 0.62, x: 40, y: 205 } as const;
const STEPS = [both, both + 12] as const;
/** How long a piece takes to cross, and when each sets off. */
const CROSSING = 8;
export const SETS_OFF: Readonly<Record<Piece, number>> = {
  title: both + 12,
  note: both + 12,
  worth: both + 19,
  todo: both + 12,
  // Each sets off as the one before arrives, and of two that stand side by side the
  // one nearer the phone goes first, so that none has to pass over another. The three markets stand side by side and go together, so none crosses another.
  markets: both + 22,
  btc: both + 22,
  gold: both + 22,
  stock: both + 22,
  coming: both + 28,
  signals: both + 25,
  // The capsule goes last, across a desk the cards have already left.
  side: both + 31,
};
/** When the sidebar becomes the capsule of places, where it stands. */
export const COLLAPSES = [both + 8, both + 16] as const;
/** When the last piece is across, and the phone's own screen takes over. */
export const HANDOVER = [both + 38, both + 43] as const;

const towards =
  (frame: number) =>
  (piece: Piece): number => {
    const at = SETS_OFF[piece];
    return tween(frame, at, at + CROSSING, 0, 1, EASE_IN_OUT);
  };

const viewAt = (frame: number): { k: number; x: number; y: number } => {
  const t = tween(frame, STEPS[0], STEPS[1], 0, 1, EASE_IN_OUT);
  return {
    k: 1 + (ASIDE.k - 1) * t,
    x: ASIDE.x * t,
    y: ASIDE.y * t,
  };
};

const built =
  (frame: number) =>
  (piece: Piece): number => {
    const [there, content] = ARRIVES[piece];
    return (
      tween(frame, there, there + 9, 0, 1, EASE) +
      tween(frame, content, content + 9, 0, 1, EASE)
    );
  };

export const DeskLayer: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SIDE - 2 || frame > close + 12) {
    return null;
  }

  // Under a question Home is dimmed; while an answer is open it stands farther back.
  const under =
    tween(frame, shot("why").from - 2, shot("why").from + 6, 0, 1, (t) => t) *
    (1 - tween(frame, both, both + 10, 0, 1, (t) => t));
  let back = 0;
  let lifted: { box: Box; by: number; press: number } | undefined;
  let hole: { box: Box; lit: number } | undefined;
  for (const id of QUESTIONS) {
    const { from, duration } = shot(id);
    const local = frame - from;
    const box = TARGET[id];
    if (!box) {
      continue;
    }
    const open = opens(id);
    back = Math.max(
      back,
      tween(local, open, open + OPENS, 0, 1, EASE_IN_OUT) *
        (1 -
          tween(local, duration - 2, duration + LEAVES - 2, 0, 1, EASE_IN_OUT)),
    );
    if (local >= SPOT(id) - 1 && local < open + 8) {
      // The dimming opens over the one card that answers the question; then the card's
      // edge lights and it lifts a little; and it is pressed as it opens.
      const gone = 1 - tween(local, open, open + 6, 0, 1, (t) => t);
      hole = {
        box,
        lit: tween(local, SPOT(id), SPOT(id) + 8, 0, 1, EASE_IN_OUT) * gone,
      };
      lifted = {
        box,
        by: settle(local, LIFT(id), 10) * gone,
        press:
          tween(local, open - 3, open, 0, 1, EASE) *
          (1 - tween(local, open, open + 5, 0, 1, EASE)),
      };
    }
  }
  const nine = tween(frame, both - 4, both + 6, 0, 1, (t) => t);
  // Home is never quite still: a slow drift, and a little nearer all the time.
  const drift = Math.sin((frame - meet) / 53) * (1 - nine);
  const near =
    1 + 0.012 * tween(frame, LANDED, both - 4, 0, 1, (t) => t) * (1 - nine);
  const dim = Math.min(under * 0.7 + back * 0.275, 1);
  const spot = hole ? onDesk(hole.box) : undefined;
  const round = hole && hole.box.h < 60 ? 20 : 26;

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          transformOrigin: "50% 45%",
          transform: `translate(${drift * 5}px, ${drift * -3}px) scale(${near - 0.05 * back})`,
        }}
      >
        <Desk
          frame={frame}
          built={built(frame)}
          alive={ALIVE}
          logo={tween(frame, LANDED - 4, LANDED + 2, 0, 1, (t) => t)}
          lifted={lifted}
          towards={towards(frame)}
          capsule={tween(frame, COLLAPSES[0], COLLAPSES[1], 0, 1, EASE_IN_OUT)}
          phone={SCREEN}
          view={viewAt(frame)}
        />
      </AbsoluteFill>
      {/* The dimming, with a soft hole over the card that answers the question. */}
      {dim > 0 && (
        <svg
          width={1920}
          height={1080}
          style={{ position: "absolute", inset: 0 }}
        >
          <defs>
            <filter id="spot-soft" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="7" />
            </filter>
            <mask id="spot">
              <rect width={1920} height={1080} fill="#fff" />
              {hole && spot && (
                <rect
                  x={spot.x - 6}
                  y={spot.y - 6 - 5 * (lifted?.by ?? 0)}
                  width={spot.w + 12}
                  height={spot.h + 12}
                  rx={round}
                  fill="#000"
                  opacity={hole.lit}
                  filter="url(#spot-soft)"
                />
              )}
            </mask>
          </defs>
          <rect
            width={1920}
            height={1080}
            fill={C.bg}
            opacity={dim}
            mask="url(#spot)"
          />
        </svg>
      )}
    </AbsoluteFill>
  );
};

/**
 * The pieces of Home as they arrive on the phone's screen in shot 9. The pieces
 * themselves pass behind the phone (DeskLayer is drawn under it); this is the same
 * pieces again, in front of the phone and cut to its screen, so each is seen to arrive
 * on the screen and nothing ever crosses the phone's edge.
 */
export const DeskOnPhone: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SETS_OFF.title || frame > HANDOVER[1]) {
    return null;
  }
  const handed = tween(frame, HANDOVER[0], HANDOVER[1], 0, 1, (t) => t);
  return (
    <AbsoluteFill
      style={{
        clipPath: `inset(${SCREEN.y}px ${1920 - SCREEN.x - SCREEN.w}px ${1080 - SCREEN.y - SCREEN.h}px ${SCREEN.x}px round 50px)`,
        opacity: 1 - handed,
      }}
    >
      <Desk
        frame={frame}
        built={built(frame)}
        alive={ALIVE}
        towards={towards(frame)}
        capsule={tween(frame, COLLAPSES[0], COLLAPSES[1], 0, 1, EASE_IN_OUT)}
        phone={SCREEN}
        view={viewAt(frame)}
        arriving
        copy="phone"
      />
    </AbsoluteFill>
  );
};
