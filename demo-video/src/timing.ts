import { Easing, interpolate } from "remotion";
import shots from "./shots.json";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** 120 beats a minute at 30 frames a second is 15 frames a beat. Every cut lands on one. */
export const BEAT = 15;

/** How long the radar line takes to go round when it changes the scene. */
export const SWEEP = 20;

export type ShotId =
  | "question"
  | "meet"
  | "phone"
  | "cards"
  | "range"
  | "risk"
  | "plan"
  | "close";

export interface Shot {
  readonly id: ShotId;
  readonly from: number;
  readonly duration: number;
  /** The radar line reveals this shot over the end of the one before. */
  readonly sweep: boolean;
}

/** shots.json is the one place a shot's start and length are written. */
export const SHOTS = shots as readonly Shot[];

export const TOTAL = SHOTS.reduce(
  (end, shot) => Math.max(end, shot.from + shot.duration),
  0,
);

export const shot = (id: ShotId): Shot => {
  const found = SHOTS.find((s) => s.id === id);
  if (!found) {
    throw new Error(`No shot called ${id}`);
  }
  return found;
};

/**
 * The film's words, as approved: what RADAR does and has. A line here is a line on
 * screen; the words between asterisks take the accent. The figure of shot 6 comes from
 * the example portfolio and stands inside its ring.
 */
export const COPY = {
  question: ["Buy now?", "Or *wait?*"],
  meet: ["Meet *RADAR.*"],
  phone: {
    lines: ["Every coin", "you hold.", "*Live.*"],
    small: "Synced from Binance by itself.",
  },
  cards: ["How every market", "feels *today.*"],
  range: {
    lines: ["Next week's range.", "*Today.*"],
    small: "From 10,000 simulated weeks.",
  },
  risk: {
    money: ["Of your", "money."],
    risk: ["Of your", "*risk.*"],
  },
  plan: {
    lines: ["What to buy next.", "And at what *price.*"],
    small: "From the plan you set.",
  },
  close: {
    lines: ["Your account.", "Your risk.", "Your *plan.*"],
    name: ["*RADAR.*"],
    last: "An analyst for everything you own.",
  },
} as const;

/** The app's two curves (index.css), so the film moves the way the product does. */
export const EASE = Easing.bezier(0.22, 1, 0.36, 1);
export const EASE_SOFT = Easing.bezier(0.3, 0.7, 0.2, 1);
export const EASE_IN = Easing.bezier(0.6, 0, 0.9, 0.4);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);

/** A value that goes from `a` to `b` between two frames and holds outside them. */
export const tween = (
  frame: number,
  start: number,
  end: number,
  a = 0,
  b = 1,
  easing: (t: number) => number = EASE,
): number =>
  interpolate(frame, [start, end], [a, b], {
    easing,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
