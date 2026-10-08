import shots from "./shots.json";

/**
 * The film's fixed facts. Shot timing lives in shots.json, which the Blender scene
 * reads as well, so the plates and the edit cannot drift apart.
 */
export const FPS = shots.fps;
export const WIDTH = shots.width;
export const HEIGHT = shots.height;
export const FRAMES = shots.frames;

export type ShotId =
  | "shot1"
  | "shot2"
  | "shot3"
  | "shot4"
  | "shot5"
  | "shot6"
  | "shot7"
  | "shot8"
  | "shot9";

export type Shot = {
  readonly id: ShotId;
  readonly name: string;
  readonly from: number;
  readonly frames: number;
};

export const SHOTS = Object.fromEntries(
  shots.shots.map((shot) => [shot.id, shot]),
) as Record<ShotId, Shot>;

/** Where a shot's rendered plate lives under public/. */
export const plateOf = (id: ShotId): string => `plates/${id}.mp4`;

/**
 * The approved copy, word for word, with the frames it is on screen within its shot.
 * Shots 3, 5 and 7 carry none. "RADAR" itself is engraved on the plate in shot 9, so
 * only the line under it is set here.
 */
export const COPY: Partial<
  Record<
    ShotId,
    { readonly text: string; readonly from: number; readonly to: number }
  >
> = {
  shot1: { text: "Everyone wants to know which way.", from: 30, to: 105 },
  shot2: { text: "The question was reasonable.", from: 88, to: 118 },
  shot4: { text: "I don't know.", from: 45, to: 73 },
  shot6: { text: "Not knowing has a shape.", from: 21, to: 82 },
  shot8: {
    text: "We looked for certainty. We found a range.",
    from: 39,
    to: 88,
  },
  shot9: { text: "It measures. You decide.", from: 22, to: 58 },
};
