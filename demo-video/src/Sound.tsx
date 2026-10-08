import { Html5Audio, Sequence, staticFile } from "remotion";
import { LIFTS, LOOK } from "./shots/Cards";
import { MARK, PHRASES } from "./shots/Close";
import { PUSH } from "./shots/Meet";
import { BLIPS, TURN } from "./shots/Phone";
import { LANDS } from "./shots/Plan";
import { HOURS, TICK } from "./shots/Question";
import { OPEN } from "./shots/Range";
import { MONEY, RISK } from "./shots/Risk";
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
const phone = shot("phone").from;
const cards = shot("cards").from;
const range = shot("range").from;
const risk = shot("risk").from;
const plan = shot("plan").from;
const close = shot("close").from;

/** How long before its loudest moment a whoosh starts, in frames. */
const SWELL = 9;

const CUES: readonly Cue[] = [
  // Shot 1: a tick on each new price, until the radar line takes the shot.
  ...Array.from({ length: HOURS - 1 }, (_, i) => ({
    file: `tick-${i % 5}`,
    at: question + (i + 1) * TICK,
  })).filter((cue) => cue.at < meet),
  // Shot 2: the radar line, the mark drawing, and the ring passing the lens.
  { file: "sweep", at: meet },
  { file: "shimmer", at: meet + 8 },
  { file: "whoosh", at: meet + PUSH[1] - 2 - SWELL },
  // Shot 3: the phone's turn, and each blip.
  { file: "whoosh", at: phone + (TURN[0] + TURN[1]) / 2 - SWELL },
  ...BLIPS.map((blip, i) => ({ file: `pop-${i}`, at: phone + blip.at })),
  // Shot 4: each pane lifting, and each state named.
  ...LIFTS.map((at, i) => ({ file: `glass-${i}`, at: cards + at })),
  ...LOOK.map((at, i) => ({ file: `pop-${i}`, at: cards + at + 4 })),
  // Shot 5: the cut opening, and the outcomes rising.
  { file: "shink", at: range + OPEN[0] },
  { file: "rise", at: range + OPEN[0] + 5 },
  // Shot 6: the radar line, the number counting twice, and where it lands.
  { file: "sweep", at: risk },
  { file: "roll", at: risk + MONEY[0] },
  { file: "roll", at: risk + RISK[0] },
  { file: "hit", at: risk + RISK[1] },
  // Shot 7: each blip landing on its price.
  ...LANDS.map((at, i) => ({ file: `click-${i}`, at: plan + at })),
  // Shot 8: each phrase, and the mark.
  ...PHRASES.map((at) => ({ file: "hit", at: close + at })),
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
