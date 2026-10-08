import { useId } from "react";
import { AbsoluteFill, spring } from "remotion";
import { C, FEATURES, FONT, fade } from "./theme";
import { EASE_IN_OUT, FPS, shot, tween, type ShotId } from "./timing";
import { Rise } from "./Type";
import type { Box } from "./ui/Desk";

/**
 * What the answers have in common now that they are one chain. Each answer is drawn in
 * the open, in the frame's own pixels, and turns into the next one: no card opens and
 * nothing goes back to Home. Near its end an answer is proved: the picture pulls back
 * and the answer is seen to be a card of the app, on a desk or on a phone; then it
 * comes forward again as it turns into the next.
 */

/** How long one answer takes to turn into the next. */
export const MORPH = 16;

export type Proved = "why" | "level" | "range" | "risk" | "plan";

/** The phone's screen in the frame while it proves an answer: in the middle. */
export const PROOF_SCREEN: Box = { x: 810, y: 214, w: 300, h: 649.4 };
/** The desktop window while it proves an answer, under a question or over one. */
const WINDOW_LOW: Box = { x: 348, y: 262, w: 1224, h: 719 };
const WINDOW_HIGH: Box = { x: 348, y: 96, w: 1224, h: 719 };
/** The window's title bar, and how large the app is drawn inside the window. */
export const BAR = 30;
export const IN_WINDOW = WINDOW_LOW.w / 1440;
/** Where a card's content goes, in the app's pixels: on a desk page, on a phone page. */
export const DESK_CONTENT: Box = { x: 320, y: 196, w: 1064, h: 404 };
export const PHONE_CONTENT: Box = { x: 28, y: 204, w: 334, h: 210 };
const IN_PHONE = PROOF_SCREEN.w / 390;

const inWindow = (window: Box): Box => ({
  x: window.x + DESK_CONTENT.x * IN_WINDOW,
  y: window.y + BAR + DESK_CONTENT.y * IN_WINDOW,
  w: DESK_CONTENT.w * IN_WINDOW,
  h: DESK_CONTENT.h * IN_WINDOW,
});
const ON_SCREEN: Box = {
  x: PROOF_SCREEN.x + PHONE_CONTENT.x * IN_PHONE,
  y: PROOF_SCREEN.y + PHONE_CONTENT.y * IN_PHONE,
  w: PHONE_CONTENT.w * IN_PHONE,
  h: PHONE_CONTENT.h * IN_PHONE,
};

export interface Proof {
  readonly device: "desk" | "phone";
  /** The device's own box in the frame while it stands: a window, or a screen. */
  readonly at: Box;
  /** What the answer fills at full size, and the place in its card it pulls back to. */
  readonly zone: Box;
  readonly into: Box;
}

/** A question stands above its answer or below it. These are the two zones left. */
export const BELOW_QUESTION: Box = { x: 128, y: 236, w: 1664, h: 776 };
export const ABOVE_QUESTION: Box = { x: 128, y: 64, w: 1664, h: 776 };

export const PROOFS: Readonly<Record<Proved, Proof>> = {
  why: {
    device: "desk",
    at: WINDOW_LOW,
    zone: BELOW_QUESTION,
    into: inWindow(WINDOW_LOW),
  },
  level: {
    device: "phone",
    at: PROOF_SCREEN,
    zone: ABOVE_QUESTION,
    into: ON_SCREEN,
  },
  range: {
    device: "phone",
    at: PROOF_SCREEN,
    zone: BELOW_QUESTION,
    into: ON_SCREEN,
  },
  risk: {
    device: "desk",
    at: WINDOW_HIGH,
    zone: ABOVE_QUESTION,
    into: inWindow(WINDOW_HIGH),
  },
  plan: {
    device: "phone",
    at: PROOF_SCREEN,
    zone: BELOW_QUESTION,
    into: ON_SCREEN,
  },
};
export const PROVED = Object.keys(PROOFS) as Proved[];

/** When an answer pulls back into its card, and when it comes forward again. */
export const pullsBack = (id: ShotId): readonly [number, number] => {
  const end = shot(id).from + shot(id).duration;
  return [end - 30, end - 15];
};
export const comesForward = (id: ShotId): readonly [number, number] => {
  const end = shot(id).from + shot(id).duration;
  return [end - 5, end + 9];
};

/** How far an answer has pulled back at a frame of the film, from 0 to 1. */
export const pulled = (id: Proved, film: number): number => {
  const [a, b] = pullsBack(id);
  const [c, d] = comesForward(id);
  return (
    tween(film, a, b, 0, 1, EASE_IN_OUT) *
    (1 - tween(film, c, d, 0, 1, EASE_IN_OUT))
  );
};

const middle = (box: Box): { x: number; y: number } => ({
  x: box.x + box.w / 2,
  y: box.y + box.h / 2,
});

export interface Lens {
  readonly id: Proved;
  /** How far back, from 0 to 1. */
  readonly back: number;
  /** How the answer is drawn: `translate(x, y) scale(k)` about the frame's corner. */
  readonly answer: string;
  /** How much larger than it stands the device is drawn, and about which point. */
  readonly device: {
    readonly k: number;
    readonly x: number;
    readonly y: number;
  };
}

/**
 * The film's one lens over the answers. Pulling back is one move: the answer becomes
 * small about a point that goes straight to its place in the card, and the device is
 * drawn by the same move, so the answer never leaves its card on the way.
 */
export const lensAt = (film: number): Lens | null => {
  for (const id of PROVED) {
    const back = pulled(id, film);
    if (back <= 0) {
      continue;
    }
    const { zone, into } = PROOFS[id];
    const rest = Math.min(into.w / zone.w, into.h / zone.h);
    const k = rest ** back;
    const from = middle(zone);
    const to = middle(into);
    const along = (1 - k) / (1 - rest);
    const x = from.x + (to.x - from.x) * along;
    const y = from.y + (to.y - from.y) * along;
    const larger = k / rest;
    return {
      id,
      back,
      answer: `translate(${x - k * from.x}px, ${y - k * from.y}px) scale(${k})`,
      device: { k: larger, x: x - larger * to.x, y: y - larger * to.y },
    };
  }
  return null;
};

/** An answer, drawn through the film's lens. `film` is the frame of the whole film. */
export const Pulled: React.FC<{
  readonly film: number;
  readonly children: React.ReactNode;
}> = ({ film, children }) => (
  <AbsoluteFill
    style={{ transformOrigin: "0 0", transform: lensAt(film)?.answer }}
  >
    {children}
  </AbsoluteFill>
);

/** How far a move goes in one frame, as a share of the whole move. */
export const rate = (
  frame: number,
  start: number,
  end: number,
  easing: (t: number) => number = EASE_IN_OUT,
): number =>
  Math.abs(
    tween(frame + 0.5, start, end, 0, 1, easing) -
      tween(frame - 0.5, start, end, 0, 1, easing),
  );

/**
 * Motion blur for the flat pieces: what is inside is blurred along the way it moves, by
 * as many pixels across and down as it is told. A shot works those out from how far its
 * pieces go this frame.
 */
export const Smear: React.FC<{
  readonly x?: number;
  readonly y?: number;
  readonly children: React.ReactNode;
}> = ({ x = 0, y = 0, children }) => {
  const id = `smear-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const across = Math.min(Math.abs(x) * 0.22, 36);
  const down = Math.min(Math.abs(y) * 0.22, 36);
  const on = across > 0.4 || down > 0.4;
  return (
    <AbsoluteFill style={{ filter: on ? `url(#${id})` : undefined }}>
      {on && (
        <svg width={0} height={0} style={{ position: "absolute" }}>
          <filter id={id} x="-6%" y="-6%" width="112%" height="112%">
            <feGaussianBlur
              stdDeviation={`${across.toFixed(2)} ${down.toFixed(2)}`}
            />
          </filter>
        </svg>
      )}
      {children}
    </AbsoluteFill>
  );
};

/**
 * The mark on an answer: four corners in the accent that start wide of it and snap in
 * to frame it, with a small overshoot, and fade as the answer turns into the next. It
 * fills the box it is put in (a box with a position of its own), `pad` pixels clear.
 */
export const Lock: React.FC<{
  readonly frame: number;
  readonly at: number;
  readonly out: number;
  readonly pad?: number;
}> = ({ frame, at, out, pad = 22 }) => {
  if (frame < at || frame > out + 6) {
    return null;
  }
  const snap = spring({
    frame: frame - at,
    fps: FPS,
    durationInFrames: 8,
    config: { damping: 11, mass: 0.5, stiffness: 190 },
  });
  const arm = 28;
  const stroke = 4;
  const corner = (right: boolean, foot: boolean): React.CSSProperties => ({
    position: "absolute",
    left: right ? undefined : 0,
    right: right ? 0 : undefined,
    top: foot ? undefined : 0,
    bottom: foot ? 0 : undefined,
    width: arm,
    height: arm,
    boxSizing: "border-box",
    borderColor: C.accent,
    borderStyle: "solid",
    borderWidth: `${foot ? 0 : stroke}px ${right ? stroke : 0}px ${foot ? stroke : 0}px ${right ? 0 : stroke}px`,
    filter: `drop-shadow(0 0 8px ${fade(C.accent, 0.6)})`,
  });
  return (
    <span
      style={{
        position: "absolute",
        inset: -pad,
        // About 40% wider than the answer, then in on to it.
        scale: String(1.4 - 0.4 * snap),
        opacity:
          tween(frame, at, at + 3, 0, 1, (t) => t) *
          (1 - tween(frame, out, out + 6, 0, 1, (t) => t)),
      }}
    >
      <span style={corner(false, false)} />
      <span style={corner(true, false)} />
      <span style={corner(false, true)} />
      <span style={corner(true, true)} />
    </span>
  );
};

/** How large a question is, and where its line starts above or below an answer. */
export const QUESTION = 96;
export const QUESTION_TOP = 80;
export const QUESTION_FOOT = 896;

/**
 * A question, in the space beside its answer: its words rise out of a mask where they
 * will stand, and leave upwards as the answer starts to turn into the next. It never
 * moves, so nothing crosses it. Words between asterisks take the accent.
 */
export const Asked: React.FC<{
  readonly line: string;
  readonly at: number;
  readonly out: number;
  readonly top: number;
  readonly left?: number;
}> = ({ line, at, out, top, left = 128 }) => {
  let lit = false;
  return (
    <div
      style={{
        position: "absolute",
        left,
        top,
        display: "flex",
        gap: "0.24em",
        whiteSpace: "nowrap",
        fontFamily: FONT,
        fontFeatureSettings: FEATURES,
        fontSize: QUESTION,
        fontWeight: 700,
        letterSpacing: "-0.03em",
        lineHeight: 1.05,
        color: C.ink,
      }}
    >
      {line.split(" ").map((raw, i) => {
        const marked = lit || raw.startsWith("*");
        lit = marked && !raw.endsWith("*");
        return (
          <Rise
            key={raw + i}
            at={at + i * 3}
            out={out}
            style={{ color: marked ? C.accent : undefined }}
          >
            {raw.split("*").join("")}
          </Rise>
        );
      })}
    </div>
  );
};

/** The frame of the film a shot's own frame is, for a shot that starts `lead` early. */
export const filmFrame = (id: ShotId, frame: number, lead = 0): number =>
  shot(id).from - lead + frame;
