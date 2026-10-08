import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ASKED, LEAVES, OPENS, TAPPED, onDesk } from "./Beat";
import * as Cal from "./shots/Calendar";
import { C, fade } from "./theme";
import { EASE, EASE_IN_OUT, shot, tween, type ShotId } from "./timing";
import { AT, BUTTON, Desk, type Box, type Piece } from "./ui/Desk";
import { Tap } from "./ui/motion";

/**
 * The app's Home, behind the whole of the film from shot 2 to shot 9. It builds itself
 * in shot 2; it stands, dimmed, under every question; the card that answers a question
 * is tapped on it; and in shot 9 it reflows into the phone's layout. It runs on the
 * film's own clock.
 */

const meet = shot("meet").from;
const both = shot("both").from;
const close = shot("close").from;

/** When the mark has landed as the logo, and the sidebar is in. */
export const LANDED = meet + 62;
/** When each piece's placeholder arrives, and when its content does. */
const ARRIVES: Readonly<Record<Piece, readonly [number, number]>> = {
  side: [meet + 50, meet + 50],
  title: [meet + 58, meet + 58],
  note: [meet + 60, meet + 60],
  worth: [meet + 62, meet + 76],
  todo: [meet + 65, meet + 79],
  markets: [meet + 68, meet + 68],
  btc: [meet + 68, meet + 82],
  gold: [meet + 71, meet + 85],
  stock: [meet + 74, meet + 88],
  coming: [meet + 77, meet + 91],
  signals: [meet + 80, meet + 94],
};
/** When the cards' content starts to move: the price ticks, the lines draw. */
export const ALIVE = meet + 78;
/** When each placeholder resolves, for the sound. */
export const RESOLVES = Object.values(ARRIVES)
  .map(([, content]) => content)
  .filter((at) => at > meet + 70);

/** The card of Home that answers each question. */
export const TARGET: Readonly<Partial<Record<ShotId, Box>>> = {
  why: AT.btc,
  level: BUTTON.check,
  range: AT.btc,
  risk: BUTTON.risk,
  plan: AT.todo,
  calendar: AT.coming,
};
const QUESTIONS = Object.keys(TARGET) as ShotId[];
const asked = (id: ShotId): number => (id === "calendar" ? Cal.ASKED : ASKED);
const tapped = (id: ShotId): number => asked(id) - (ASKED - TAPPED);

/** When the tap falls for each question, in film frames, for the sound. */
export const TAPS = QUESTIONS.map((id) => shot(id).from + tapped(id));

/** The phone's screen in the frame, which Home reflows into in shot 9 (shots/Both). */
export const SCREEN: Box = { x: 1262, y: 168, w: 352, h: 762 };
/** When Home reflows into the phone's layout. */
export const MORPH = [both + 2, both + 20] as const;
/** When the phone's own screen takes over from the reflowed pieces. */
export const HANDOVER = [both + 20, both + 27] as const;

export const DeskLayer: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < meet + 48 || frame > close + 12) {
    return null;
  }
  const built = (piece: Piece): number => {
    const [there, content] = ARRIVES[piece];
    return (
      tween(frame, there, there + 9, 0, 1, EASE) +
      tween(frame, content, content + 9, 0, 1, EASE)
    );
  };

  // Under a question Home is dimmed; while an answer is open it stands farther back.
  const under =
    tween(frame, shot("why").from - 2, shot("why").from + 6, 0, 1, (t) => t) *
    (1 - tween(frame, both, both + 10, 0, 1, (t) => t));
  let back = 0;
  let pressed: { box: Box; by: number } | undefined;
  let tap: { since: number; box: Box } | undefined;
  for (const id of QUESTIONS) {
    const { from, duration } = shot(id);
    const local = frame - from;
    const box = TARGET[id];
    if (!box) {
      continue;
    }
    back = Math.max(
      back,
      tween(local, asked(id), asked(id) + OPENS, 0, 1, EASE_IN_OUT) *
        (1 -
          tween(local, duration - 2, duration + LEAVES - 2, 0, 1, EASE_IN_OUT)),
    );
    const at = tapped(id);
    if (local >= at - 1 && local < at + 18) {
      const by =
        tween(local, at, at + 3, 0, 1, EASE) *
        (1 - tween(local, at + 3, at + 10, 0, 1, EASE));
      pressed = { box, by };
      tap = { since: local - at, box };
    }
  }
  const morph = tween(frame, MORPH[0], MORPH[1], 0, 1, EASE_IN_OUT);
  const handed = tween(frame, HANDOVER[0], HANDOVER[1], 0, 1, (t) => t);
  // Home is never quite still: a slow drift, and a little nearer all the time.
  const drift = Math.sin((frame - meet) / 53);
  const near = 1 + 0.012 * tween(frame, LANDED, both, 0, 1, (t) => t);
  const spot = tap ? onDesk(tap.box) : undefined;

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          transformOrigin: "50% 45%",
          transform: `translate(${drift * 5 * (1 - morph)}px, ${drift * -3 * (1 - morph)}px) scale(${(near - 0.05 * back) * (1 - morph) + morph})`,
          opacity: 1 - handed,
        }}
      >
        <Desk
          frame={frame}
          built={built}
          alive={ALIVE}
          logo={tween(frame, LANDED - 4, LANDED + 2, 0, 1, (t) => t)}
          pressed={pressed}
          morph={morph}
          phone={SCREEN}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          backgroundColor: fade(C.bg, 1),
          opacity: under * 0.7 + back * 0.275,
        }}
      />
      {tap && spot && (
        <Tap
          since={tap.since}
          x={spot.x + spot.w * 0.5}
          y={spot.y + spot.h * 0.5}
        />
      )}
    </AbsoluteFill>
  );
};
