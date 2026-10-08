import { Html5Audio, Sequence, staticFile } from "remotion";
import { comesForward, PROVED, pullsBack } from "./Chain";
import {
  ALIVE,
  COLLAPSES,
  HANDOVER,
  LANDED,
  RESOLVES,
  SETS_OFF,
} from "./DeskLayer";
import { SLIDES } from "./Devices";
import * as Cal from "./shots/Calendar";
import { MARK } from "./shots/Close";
import * as Level from "./shots/Level";
import * as Mark from "./shots/Meet";
import * as Plan from "./shots/Plan";
import * as Coin from "./shots/Question";
import * as Far from "./shots/Range";
import * as Mix from "./shots/Risk";
import * as Why from "./shots/Why";
import { FPS, LAST_SWEEP, TOTAL, shot, type ShotId } from "./timing";

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
  lock: 0.14,
  dive: 0.6,
};

/**
 * How loud each kind of sound is in the film, from 0 to 1. This is the mix. With each
 * file's own peak (sound/make_sfx.py), the hits sit near -6 dB of full scale and the
 * lock's tick near -14.
 */
const LEVEL: Readonly<Record<string, number>> = {
  room: 0.04,
  tick: 0.2,
  sweep: 0.7,
  shimmer: 0.55,
  whoosh: 0.7,
  pop: 0.45,
  glass: 0.5,
  shink: 0.75,
  rise: 0.5,
  roll: 0.6,
  click: 0.6,
  hit: 0.8,
  impact: 1,
  spin: 0.6,
  topple: 0.55,
  clink: 0.8,
  chip: 0.8,
  flip: 0.6,
  bars: 0.7,
  slide: 0.6,
  flap: 0.6,
  thunk: 0.85,
  lock: 0.55,
  dive: 0.55,
};

interface Cue {
  /** The sound's file name without its ending: "pop-1". */
  readonly file: string;
  /** The frame of the film it starts on. */
  readonly at: number;
  /** Its level here, where it is not the usual one for its kind. */
  readonly level?: number;
}

const at = (id: ShotId): number => shot(id).from;
const question = at("question");
const meet = at("meet");

/** The answers, and how early the change into each one starts. */
const TURNS_INTO: readonly (readonly [ShotId, number])[] = [
  ["why", Why.LEAD],
  ["level", 0],
  ["range", 0],
  ["risk", 0],
  ["plan", 0],
  ["calendar", 0],
];

const CUES: readonly Cue[] = [
  // Shot 1: the coin spinning, going over and rattling round its rim; its landing; a
  // knock from each of the three words; its flick back up on to its rim and its spin
  // round to face us. Under it, quietly, a tick on each new price.
  { file: "spin", at: question },
  { file: "topple", at: question + Coin.TOPPLE + 4 },
  { file: "clink", at: question + Coin.LANDS },
  ...Coin.WORDS.map((w) => ({ file: "clink", at: question + w, level: 0.4 })),
  { file: "flip", at: question + Coin.EXIT - 1 },
  { file: "spin", at: question + Coin.EXIT + 1, level: 0.5 },
  ...Array.from({ length: Coin.HOURS - 1 }, (_, i) => ({
    file: `tick-${i % 5}`,
    at: question + (i + 1) * Coin.TICK,
  })),

  // Shot 2: the coin turning into the mark; the radar's line inside the ring; the dot
  // landing; the mark's flight to the sidebar and its landing there; and each card's
  // content arriving.
  { file: "shimmer", at: meet - 4 },
  { file: "sweep", at: meet + Mark.TURNS[0], level: 0.4 },
  { file: "pop-1", at: meet + Mark.DOT },
  { file: "dive", at: LANDED - 18 },
  { file: "thunk", at: LANDED - 1 },
  ...RESOLVES.map((frame, i) => ({
    file: `glass-${i % 3}`,
    at: frame,
    level: 0.3,
  })),
  { file: "rise", at: ALIVE },

  // Every change of one answer into the next: a soft rush of air.
  ...TURNS_INTO.map(([id, lead]) => ({
    file: "whoosh",
    at: at(id) - lead - 1,
    level: 0.4,
  })),
  // Every proof: the camera pulling back, and the answer settling into its card.
  ...PROVED.flatMap((id) => [
    { file: "dive", at: pullsBack(id)[0], level: 0.4 },
    {
      file: `glass-${PROVED.indexOf(id) % 3}`,
      at: pullsBack(id)[1],
      level: 0.3,
    },
    { file: "dive", at: comesForward(id)[0], level: 0.3 },
  ]),

  // Shot 3: the days growing, the crosshair's slide, the day's bar dropping, its
  // figures popping up, and the lock on them.
  { file: "bars", at: at("why") + Why.BARS },
  { file: "slide", at: at("why") + Why.CROSS[0] + 2 },
  { file: "hit", at: at("why") + Why.DROP + 2 },
  { file: "pop-1", at: at("why") + Why.TIP },
  { file: "lock", at: at("why") + Why.LOCKED },

  // Shot 4: each bead sliding to its place, and the lock.
  ...[0, 1, 2, 3, 4].map((i) => ({
    file: "slide",
    at: at("level") + Level.BEADS + i * Level.EVERY,
  })),
  { file: "lock", at: at("level") + Level.LOCKED },

  // Shot 5: the beads meeting, the cut opening, the two figures counting, the outcomes
  // growing, and the lock on the range.
  { file: "pop-2", at: at("range") + 9 },
  { file: "shink", at: at("range") + Far.OPEN[0] },
  { file: "roll", at: at("range") + Far.OPEN[0] + 12 },
  { file: "bars", at: at("range") + Far.RISE },
  { file: "lock", at: at("range") + Far.LOCKED },

  // Shot 6: the bar filling, the same bar weighed again and its figures rolling, and
  // the lock on Bitcoin's share.
  { file: "slide", at: at("risk") + Mix.FILL[0] },
  { file: "roll", at: at("risk") + Mix.REWEIGH - 1 },
  { file: "hit", at: at("risk") + Mix.REWEIGH + 4, level: 0.5 },
  { file: "lock", at: at("risk") + Mix.LOCKED },

  // Shot 7: the bar reshaping, the ladder's line running out, each coin landing on its
  // price, and the lock.
  { file: "slide", at: at("plan") + Plan.RESHAPE[0] },
  { file: "slide", at: at("plan") + Plan.RUNS[0] },
  ...Plan.LANDS.map((frame, i) => ({
    file: `chip-${i}`,
    at: at("plan") + frame,
  })),
  { file: "lock", at: at("plan") + Plan.LOCKED },

  // Shot 8: the rows, the count of days rolling down, the lock, and the rows flying to
  // their places on Home.
  ...[0, 1, 2, 3].map((i) => ({
    file: `pop-${i % 3}`,
    at: at("calendar") + Cal.ROWS + i * Cal.EVERY,
    level: 0.3,
  })),
  { file: "flap", at: at("calendar") + Cal.ROLL[0] },
  { file: "lock", at: at("calendar") + Cal.LOCKED },
  { file: "dive", at: at("calendar") + Cal.FLIES, level: 0.4 },
  { file: "thunk", at: at("calendar") + Cal.LANDED - 1, level: 0.5 },

  // Shot 9: the phone coming up, the sidebar becoming the capsule, each card arriving
  // on the screen, and the phone's own screen taking over.
  { file: "dive", at: at("both") + SLIDES[0] },
  { file: "whoosh", at: COLLAPSES[0], level: 0.4 },
  ...(["worth", "todo", "btc", "gold", "stock"] as const).map((piece, i) => ({
    file: `pop-${i % 3}`,
    at: SETS_OFF[piece] + 7,
    level: 0.35,
  })),
  { file: "thunk", at: HANDOVER[0] + 1 },

  // Shot 10: the radar's line, quickly, and the mark.
  { file: "sweep", at: at("close") - 4 },
  { file: "impact", at: at("close") + LAST_SWEEP - 4 + MARK },
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
    {CUES.map((cue, i) => {
      const level = cue.level ?? LEVEL[kind(cue.file)];
      const frames = Math.ceil(LENGTH[kind(cue.file)] * FPS) + 1;
      const from = Math.round(cue.at);
      if (from >= TOTAL) {
        return null;
      }
      return (
        <Sequence
          key={`${cue.file}-${from}-${i}`}
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
