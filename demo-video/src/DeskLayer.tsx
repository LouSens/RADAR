import { AbsoluteFill, useCurrentFrame } from "remotion";
import * as Cal from "./shots/Calendar";
import { PUSHED_FROM, pushAt } from "./shots/Why";
import { EASE, EASE_IN_OUT, shot, tween } from "./timing";
import { Desk, type Box, type Piece } from "./ui/Desk";

/**
 * The app's Home. It is in the film twice: in shot 2, where it builds itself round the
 * mark and the camera then pushes into its Bitcoin card; and from the end of shot 8,
 * where it comes back under the calendar's rows and, in shot 9, steps aside for the
 * phone and its pieces go across to the phone's screen one at a time. Between the two
 * the answers turn into one another without it. It runs on the film's own clock.
 */

const meet = shot("meet").from;
const why = shot("why").from;
const calendar = shot("calendar").from;
const both = shot("both").from;
const close = shot("close").from;

/** When the mark has landed as the logo. The sidebar is in a little before. */
export const LANDED = meet + 62;
const SIDE = LANDED - 12;
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

/** When Home has gone, pushed into, and when it comes back under the calendar. */
const GONE = why + 1;
const BACK = [calendar + Cal.FLIES, calendar + Cal.FLIES + 5] as const;
/** When the calendar's rows have landed in Home's own card. */
const ROWS_IN = calendar + Cal.LANDED;

// Shot 9. The phone comes in first; Home steps to the left to give it room; the sidebar
// becomes the capsule of places; then each card goes across, one after another.

/** The phone's screen in the frame (PhoneLayer puts the phone there). */
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
  // one nearer the phone goes first, so that none has to pass over another. The three
  // markets stand side by side and go together.
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
    if (frame > GONE) {
      // Back round the calendar's rows, Home is whole.
      return 2;
    }
    const [there, content] = ARRIVES[piece];
    return (
      tween(frame, there, there + 9, 0, 1, EASE) +
      tween(frame, content, content + 9, 0, 1, EASE)
    );
  };

export const DeskLayer: React.FC = () => {
  const frame = useCurrentFrame();
  const early = frame >= SIDE - 2 && frame <= GONE;
  const late = frame >= BACK[0] && frame <= close + 12;
  if (!early && !late) {
    return null;
  }

  // Shot 2 to 3: one push into the Bitcoin card, about the week's line in it, and
  // Home goes as it is passed through.
  const push = pushAt(frame);
  const pushed = early
    ? `translate(${push.x - push.k * PUSHED_FROM.x}px, ${push.y - push.k * PUSHED_FROM.y}px) scale(${push.k})`
    : undefined;
  const passed = early ? 1 - tween(frame, why - 9, why - 2, 0, 1, (t) => t) : 1;
  // Shot 8 to 9: it comes back round the calendar's rows, as a camera pulling away
  // from them shows it, its own rows empty until theirs have landed.
  const back = tween(frame, BACK[0], BACK[1], 0, 1, (t) => t);
  const home = Cal.homeAt(frame - calendar);
  const pulled = `translate(${home.x}px, ${home.y}px) scale(${home.k})`;
  // Home is never quite still: a slow drift, and a little nearer all the time.
  const drift = early ? Math.sin((frame - meet) / 53) : 0;
  const near = early
    ? 1 + 0.012 * tween(frame, LANDED, why, 0, 1, (t) => t)
    : 1;

  return (
    <AbsoluteFill
      style={{
        opacity: early ? passed : back,
      }}
    >
      <AbsoluteFill
        style={{ transformOrigin: "0 0", transform: early ? pushed : pulled }}
      >
        <AbsoluteFill
          style={{
            transformOrigin: "50% 45%",
            transform: `translate(${drift * 5}px, ${drift * -3}px) scale(${near})`,
          }}
        >
          <Desk
            frame={frame}
            built={built(frame)}
            alive={ALIVE}
            logo={tween(frame, LANDED - 4, LANDED + 2, 0, 1, (t) => t)}
            towards={towards(frame)}
            capsule={tween(
              frame,
              COLLAPSES[0],
              COLLAPSES[1],
              0,
              1,
              EASE_IN_OUT,
            )}
            phone={SCREEN}
            view={viewAt(frame)}
            coming={
              early ? 1 : tween(frame, ROWS_IN - 2, ROWS_IN + 2, 0, 1, (t) => t)
            }
          />
        </AbsoluteFill>
      </AbsoluteFill>
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
