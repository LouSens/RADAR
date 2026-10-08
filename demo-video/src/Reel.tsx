import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { LEAVES } from "./Beat";
import { DeskLayer } from "./DeskLayer";
import { Grain } from "./Grain";
import { Ground } from "./Ground";
import { Opening, Questions } from "./Questions";
import { Both } from "./shots/Both";
import { Calendar } from "./shots/Calendar";
import { Close } from "./shots/Close";
import { Level } from "./shots/Level";
import { Meet } from "./shots/Meet";
import { Plan } from "./shots/Plan";
import { Question } from "./shots/Question";
import { Range } from "./shots/Range";
import { Risk } from "./shots/Risk";
import { Why } from "./shots/Why";
import { Sound } from "./Sound";
import { SweepLine, Swept } from "./Sweep";
import { AssetsProvider, useAssets } from "./three/assets";
import { FPS, LAST_SWEEP, SWEEP, shot, type ShotId } from "./timing";

/** The answers, each opening out of a card of Home and going back into it. */
const ANSWERS: readonly (readonly [ShotId, React.ReactNode])[] = [
  ["why", <Why key="why" />],
  ["level", <Level key="level" />],
  ["range", <Range key="range" />],
  ["risk", <Risk key="risk" />],
  ["plan", <Plan key="plan" />],
  ["calendar", <Calendar key="calendar" />],
];

/**
 * The reel: one situation, answered by the app. Bitcoin falls, as a coin (shot 1); the
 * radar's line takes the coin away and the mark is drawn, lands as the app's logo, and
 * Home builds itself round it (shot 2); each question is then answered out of a card of
 * Home (shots 3 to 8); Home reflows on to the phone (shot 9); and the line uncovers the
 * end card. Only the coin, the mark and the phone are objects: all the data is the
 * app's own elements, moving. Every shot's start and length are in shots.json.
 */
export const Reel: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useAssets();
  const question = shot("question");
  const meet = shot("meet");
  const both = shot("both");
  const close = shot("close");

  return (
    <AssetsProvider value={assets}>
      <AbsoluteFill>
        <Ground />
        <Sound />
        <Swept since={frame - close.from} side="out" length={LAST_SWEEP}>
          <Swept since={frame - meet.from} side="out">
            <Sequence
              name="1 question"
              from={question.from}
              durationInFrames={question.duration + SWEEP}
              premountFor={FPS}
            >
              <Question />
            </Sequence>
            <Opening />
          </Swept>
          <Swept since={frame - meet.from} side="in">
            <Sequence
              name="9 both"
              from={both.from}
              durationInFrames={both.duration + LAST_SWEEP}
              premountFor={FPS}
            >
              <Both />
            </Sequence>
            {/* Home and the questions run on the film's own clock, not a shot's. */}
            <DeskLayer />
            <Sequence
              name="2 meet"
              from={meet.from}
              durationInFrames={meet.duration}
              premountFor={FPS}
            >
              <Meet />
            </Sequence>
            {ANSWERS.map(([id, picture]) => (
              <Sequence
                key={id}
                name={id}
                from={shot(id).from}
                durationInFrames={shot(id).duration + LEAVES}
                premountFor={FPS}
              >
                {picture}
              </Sequence>
            ))}
            <Questions />
          </Swept>
        </Swept>
        <Sequence
          name="10 close"
          from={close.from}
          durationInFrames={close.duration}
          premountFor={FPS}
        >
          <Swept since={frame - close.from} side="in" length={LAST_SWEEP}>
            <Close />
          </Swept>
        </Sequence>
        <SweepLine since={frame - meet.from} />
        <SweepLine since={frame - close.from} length={LAST_SWEEP} />
        <Grain />
      </AbsoluteFill>
    </AssetsProvider>
  );
};
