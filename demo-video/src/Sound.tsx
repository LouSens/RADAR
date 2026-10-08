import { Html5Audio, Sequence, staticFile } from "remotion";
import { MARK } from "./shots/Close";
import { HOURS, TICK } from "./shots/Question";
import { FPS, TOTAL, shot } from "./timing";

/**
 * The film's sound: effects only, no music. Every sound is made by sound/make_sfx.py
 * (public/sfx). Each cue takes its frame from the animation it belongs to, so a move
 * that is retimed takes its sound with it. The type's entries and exits have no sound.
 */

/** The airy tone under the whole film. Set this to false to turn it off. */
const ROOM = true;

/** How long each sound is, in seconds (sound/make_sfx.py). */
const LENGTH: Readonly<Record<string, number>> = {
  tick: 0.02,
  sweep: 0.8,
  shimmer: 1.5,
  whoosh: 0.5,
  pop: 0.16,
  glass: 0.4,
  shink: 0.6,
  rise: 1.5,
  roll: 0.75,
  click: 0.3,
  hit: 0.3,
  impact: 2.2,
};

/** How loud each kind of sound is in the film, from 0 to 1. This is the mix. */
const LEVEL: Readonly<Record<string, number>> = {
  room: 0.04,
  tick: 0.45,
  sweep: 0.7,
  shimmer: 0.55,
  whoosh: 0.8,
  pop: 0.65,
  glass: 0.65,
  shink: 0.75,
  rise: 0.55,
  roll: 0.6,
  click: 0.75,
  hit: 0.8,
  impact: 1,
};

interface Cue {
  /** The sound's file name without its ending: "pop-1". */
  readonly file: string;
  /** The frame of the film it starts on. */
  readonly at: number;
}

const question = shot("question").from;
const meet = shot("meet").from;
const close = shot("close").from;

// The animatic's sheet: only the sounds whose pictures are already in the film. The
// pings, the dives and the live pictures' own sounds are cued when those are built.
const CUES: readonly Cue[] = [
  // Shot 1: a tick on each new price.
  ...Array.from({ length: HOURS - 1 }, (_, i) => ({
    file: `tick-${i % 5}`,
    at: question + (i + 1) * TICK,
  })).filter((cue) => cue.at < meet),
  // Shot 2: the mark drawing.
  { file: "shimmer", at: meet + 8 },
  // Shot 10: the radar line, and the mark.
  { file: "sweep", at: close },
  { file: "impact", at: close + MARK },
];

const kind = (file: string): string => file.split("-")[0];

export const Sound: React.FC = () => (
  <>
    {ROOM && (
      <Sequence durationInFrames={TOTAL} layout="none" name="room">
        <Html5Audio
          src={staticFile("sfx/room.wav")}
          volume={() => LEVEL.room}
        />
      </Sequence>
    )}
    {CUES.map((cue) => {
      const level = LEVEL[kind(cue.file)];
      const frames = Math.ceil(LENGTH[kind(cue.file)] * FPS) + 1;
      const from = Math.round(cue.at);
      return (
        <Sequence
          key={`${cue.file}-${from}`}
          from={from}
          durationInFrames={Math.min(frames, TOTAL - from)}
          layout="none"
          name={cue.file}
        >
          <Html5Audio
            src={staticFile(`sfx/${cue.file}.wav`)}
            volume={() => level}
          />
        </Sequence>
      );
    })}
  </>
);
