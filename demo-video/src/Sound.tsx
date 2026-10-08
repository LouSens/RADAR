import { Html5Audio, Sequence, staticFile } from "remotion";
import {
  ALIVE,
  HANDOVER,
  LANDED,
  LIFTS,
  OPENINGS,
  RESOLVES,
  SETS_OFF,
} from "./DeskLayer";
import * as Phone from "./shots/Both";
import * as Cal from "./shots/Calendar";
import { MARK } from "./shots/Close";
import * as Level from "./shots/Level";
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
  ping: 1.4,
  dive: 0.6,
};

/**
 * How loud each kind of sound is in the film, from 0 to 1. This is the mix. With each
 * file's own peak (sound/make_sfx.py), the hits sit near -6 dB of full scale and the
 * pings near -16.
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
  ping: 0.4,
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

/** The questions that are answered out of a card, and when each one's card opens. */
const ANSWERED: readonly ShotId[] = [
  "why",
  "level",
  "range",
  "risk",
  "plan",
  "calendar",
];

const CUES: readonly Cue[] = [
  // Shot 1: the coin spinning, going over and rattling round its rim; its landing; a
  // knock from each of the three words; and its roll out of the frame. Under it,
  // quietly, a tick on each new price.
  { file: "spin", at: question },
  { file: "topple", at: question + Coin.TOPPLE + 4 },
  { file: "clink", at: question + Coin.LANDS },
  ...Coin.WORDS.map((w) => ({ file: "clink", at: question + w, level: 0.4 })),
  { file: "roll", at: question + Coin.EXIT + 2 },
  ...Array.from({ length: Coin.HOURS - 1 }, (_, i) => ({
    file: `tick-${i % 5}`,
    at: question + (i + 1) * Coin.TICK,
  })).filter((cue) => cue.at < question + Coin.EXIT),

  // Shot 2: the radar's line; the mark drawing; its flight to the sidebar and its
  // landing there; and each card's content arriving.
  { file: "sweep", at: meet },
  { file: "shimmer", at: meet + 8 },
  { file: "dive", at: LANDED - 18 },
  { file: "thunk", at: LANDED - 1 },
  ...RESOLVES.map((frame, i) => ({
    file: `glass-${i % 3}`,
    at: frame,
    level: 0.3,
  })),
  { file: "rise", at: ALIVE },

  // Every answered question: its card lifting, a soft click as it is pressed and
  // opens out, and the answer going back into its card as the next question arrives.
  ...LIFTS.map((frame, i) => ({
    file: `glass-${i % 3}`,
    at: frame,
    level: 0.3,
  })),
  ...OPENINGS.map((frame, i) => ({ file: `click-${i % 3}`, at: frame - 1 })),
  ...OPENINGS.map((frame) => ({ file: "dive", at: frame })),
  ...ANSWERED.map((id) => ({
    file: "flip",
    at: at(id) + shot(id).duration - 4,
    level: 0.4,
  })),

  // Shot 3: the days growing, the crosshair's slide, the push in, the day's bar
  // dropping, its figures popping up, the ring, and the card arriving.
  { file: "bars", at: at("why") + Why.BARS },
  { file: "slide", at: at("why") + Why.CROSS[0] + 2 },
  { file: "whoosh", at: at("why") + Why.PUSH[0] - 4, level: 0.45 },
  { file: "hit", at: at("why") + Why.DROP + 2 },
  { file: "pop-1", at: at("why") + Why.TIP },
  { file: "ping", at: at("why") + Why.PINGED },
  { file: "glass-1", at: at("why") + Why.FRAMED + 8, level: 0.35 },

  // Shot 4: each bead sliding to its place, and the ring.
  ...[0, 1, 2, 3, 4].map((i) => ({
    file: "slide",
    at: at("level") + Level.BEADS + i * Level.EVERY,
  })),
  { file: "glass-2", at: at("level") + Level.FRAMED + 10, level: 0.35 },
  { file: "ping", at: at("level") + Level.PINGED },

  // Shot 5: the cut opening, the two figures counting, the outcomes growing, the badge,
  // and the ring on the range.
  { file: "shink", at: at("range") + Far.OPEN[0] },
  { file: "roll", at: at("range") + Far.OPEN[0] + 12 },
  { file: "bars", at: at("range") + Far.RISE },
  { file: "pop-0", at: at("range") + Far.FRAMED + 10 },
  { file: "ping", at: at("range") + Far.PINGED },

  // Shot 6: the money ring and the count to it, each row, the risk ring and the count
  // on, Bitcoin's piece swelling, and the ring on its row.
  { file: "roll", at: at("risk") + Mix.MONEY[0] },
  ...[0, 1, 2, 3].map((i) => ({
    file: `pop-${i % 3}`,
    at: at("risk") + Mix.ROWS + i * Mix.EVERY,
    level: 0.3,
  })),
  { file: "roll", at: at("risk") + Mix.RISK[0] },
  { file: "hit", at: at("risk") + Mix.SWELL + 2 },
  { file: "ping", at: at("risk") + Mix.PINGED },

  // Shot 7: the bar reshaping, each coin landing on its price, and the ring.
  { file: "slide", at: at("plan") + Plan.RESHAPE[0] },
  ...Plan.LANDS.map((frame, i) => ({
    file: `chip-${i}`,
    at: at("plan") + frame,
  })),
  { file: "ping", at: at("plan") + Plan.PINGED },

  // Shot 8: the rows, the count of days rolling down, and the ring.
  ...[0, 1, 2, 3].map((i) => ({
    file: `pop-${i % 3}`,
    at: at("calendar") + Cal.ROWS + i * Cal.EVERY,
    level: 0.3,
  })),
  { file: "flap", at: at("calendar") + Cal.ROLL[0] },
  { file: "ping", at: at("calendar") + Cal.PINGED },

  // Shot 9: the phone coming up, the sidebar becoming the capsule, each card arriving
  // on the screen, and the phone's own screen taking over.
  { file: "dive", at: at("both") + Phone.SLIDES[0] },
  { file: "whoosh", at: SETS_OFF.side, level: 0.4 },
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
    {CUES.map((cue) => {
      const level = cue.level ?? LEVEL[kind(cue.file)];
      const frames = Math.ceil(LENGTH[kind(cue.file)] * FPS) + 1;
      const from = Math.round(cue.at);
      if (from >= TOTAL) {
        return null;
      }
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
