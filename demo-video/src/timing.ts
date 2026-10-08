import shots from "./shots.json";

/**
 * The film's fixed facts. shots.json is the one place a beat's start and length are
 * written; everything else reads it.
 */
export const FPS = shots.fps;
export const WIDTH = shots.width;
export const HEIGHT = shots.height;
export const FRAMES = shots.frames;

export type BeatId =
  | "beat1"
  | "beat2"
  | "beat3"
  | "beat4"
  | "beat5"
  | "beat6"
  | "beat7";

export type Beat = {
  readonly id: BeatId;
  readonly name: string;
  readonly from: number;
  readonly frames: number;
};

export const BEATS = Object.fromEntries(
  shots.shots.map((beat) => [beat.id, beat]),
) as Record<BeatId, Beat>;

/**
 * The approved copy, word for word, with the frames it is on screen counted from the
 * start of its own beat.
 */
export const COPY: Record<
  BeatId,
  { readonly text: string; readonly from: number; readonly to: number }
> = {
  beat1: { text: "Payday. Now what?", from: 10, to: 92 },
  beat2: { text: "Everyone has a tip.", from: 22, to: 112 },
  beat3: {
    text: "Meet RADAR. It starts with what you already own.",
    from: 30,
    to: 88,
  },
  beat4: { text: "Where your money sits.", from: 20, to: 140 },
  beat5: { text: "Where your risk sits.", from: 20, to: 140 },
  beat6: { text: "And where this month's money goes.", from: 20, to: 140 },
  beat7: { text: "No tips. No trades.", from: 14, to: 70 },
};

/** The closing line, under the mark at the end of beat 7. */
export const SIGN_OFF = "It measures. You decide.";
