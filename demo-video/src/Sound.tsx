import { Html5Audio, Sequence, staticFile } from "remotion";
import { MARK } from "./shots/Close";
import * as Coin from "./shots/Question";
import * as Far from "./shots/Range";
import * as Mix from "./shots/Risk";
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
  spin: 0.9,
  topple: 1.6,
  clink: 0.5,
  chip: 0.3,
  flip: 0.45,
  bars: 1.3,
  slide: 0.35,
  flap: 0.7,
  thunk: 0.3,
  ping: 1.4,
  dive: 0.6,
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
  spin: 0.6,
  topple: 0.55,
  // The hits sit near -6 dB of full scale and the pings near -16 (sound/make_sfx.py
  // gives each file's own peak).
  clink: 0.8,
  chip: 0.8,
  flip: 0.7,
  bars: 0.7,
  slide: 0.6,
  flap: 0.7,
  thunk: 0.85,
  ping: 0.4,
  dive: 0.6,
};

interface Cue {
  /** The sound's file name without its ending: "pop-1". */
  readonly file: string;
  /** The frame of the film it starts on. */
  readonly at: number;
  /** Its level here, where it is not the usual one for its kind. */
  readonly level?: number;
}

const question = shot("question").from;
const meet = shot("meet").from;
const range = shot("range").from;
const risk = shot("risk").from;
const close = shot("close").from;

/** How long before its loudest moment a whoosh starts, in frames. */
const SWELL = 9;

// The sheet so far: shots 1, 5, 6 and the end card are whole. The other shots get
// their sounds when their pictures are built.
const CUES: readonly Cue[] = [
  // Shot 1: the coin spinning, going over and rattling round its rim; its landing; and
  // a knock from each of the three words. Under it, quietly, a tick on each new price.
  { file: "spin", at: question },
  { file: "topple", at: question + Coin.TOPPLE + 4 },
  { file: "clink", at: question + Coin.LANDS },
  ...Coin.WORDS.map((at) => ({ file: "clink", at: question + at, level: 0.4 })),
  ...Array.from({ length: Coin.HOURS - 1 }, (_, i) => ({
    file: `tick-${i % 5}`,
    at: question + (i + 1) * Coin.TICK,
    level: 0.2,
  })).filter((cue) => cue.at < meet),
  // Shot 2: the mark drawing.
  { file: "shimmer", at: meet + 8 },
  // Shot 5: the cut opening, the two figures counting, the bars rising, the picture
  // folding into the card, and the ring on the range.
  { file: "shink", at: range + Far.OPEN[0] },
  { file: "roll", at: range + Far.OPEN[0] + 10 },
  { file: "bars", at: range + Far.RISE },
  { file: "flip", at: range + Far.FOLD[0] },
  { file: "ping", at: range + Far.PINGED },
  // Shot 6: each holding arriving, the change to shares of the risk, the number
  // landing with its ring, and the picture folding into the card.
  ...[0, 1, 2, 3].map((i) => ({
    file: `pop-${i}`,
    at: risk + Mix.MONEY[0] + i * 3,
    level: 0.4,
  })),
  { file: "whoosh", at: risk + Mix.RISK[0] - SWELL },
  { file: "roll", at: risk + Mix.RISK[0] },
  { file: "hit", at: risk + Mix.RISK[1] - 2 },
  { file: "ping", at: risk + Mix.RISK[1] },
  { file: "flip", at: risk + Mix.FOLD[0] },
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
      const level = cue.level ?? LEVEL[kind(cue.file)];
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
