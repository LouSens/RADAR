import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { DeskLayer, DeskOnPhone } from "./DeskLayer";
import { PHONE_FROM, PhoneLayer, Window } from "./Devices";
import { Grain } from "./Grain";
import { Ground } from "./Ground";
import { Opening, Questions } from "./Questions";
import { Calendar } from "./shots/Calendar";
import { Close } from "./shots/Close";
import { Level } from "./shots/Level";
import { Meet } from "./shots/Meet";
import { Plan } from "./shots/Plan";
import { GIVES, Question } from "./shots/Question";
import { Range } from "./shots/Range";
import { Risk } from "./shots/Risk";
import { LEAD, Why } from "./shots/Why";
import { Sound } from "./Sound";
import { RollBlur } from "./ui/motion";
import { SweepLine, Swept } from "./Sweep";
import { AssetsProvider, useAssets } from "./three/assets";
import { FPS, LAST_SWEEP, shot, type ShotId } from "./timing";

/** The answers, each turning into the next, and how early each one starts. */
const ANSWERS: readonly (readonly [ShotId, React.ReactNode, number])[] = [
  ["why", <Why key="why" />, LEAD],
  ["level", <Level key="level" />, 0],
  ["range", <Range key="range" />, 0],
  ["risk", <Risk key="risk" />, 0],
  ["plan", <Plan key="plan" />, 0],
  ["calendar", <Calendar key="calendar" />, 0],
];

/**
 * The reel: one situation, answered by the app, as one chain of changes. Bitcoin falls,
 * as a coin (shot 1); the coin's rim becomes the mark's ring, the mark lands as the
 * app's logo and Home builds itself round it (shot 2); the camera pushes into Home's
 * Bitcoin card, and from there each answer turns into the next, each one proved on the
 * way as a card of the app on a desk or a phone (shots 3 to 8); the last one's rows fly
 * back into Home, which reflows on to the phone (shot 9); and the radar's line uncovers
 * the end card. Only the coin, the mark and the phone are objects: all the data is the
 * app's own elements, moving. Every shot's start and length are in shots.json.
 */
export const Reel: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useAssets();
  const question = shot("question");
  const meet = shot("meet");
  const close = shot("close");

  return (
    <AssetsProvider value={assets}>
      <AbsoluteFill>
        <Ground />
        <RollBlur />
        <Sound />
        <Swept since={frame - close.from} side="out" length={LAST_SWEEP}>
          <Sequence
            name="1 question"
            from={question.from}
            durationInFrames={question.duration + GIVES}
            premountFor={FPS}
          >
            <Question />
          </Sequence>
          <Opening />
          {/* Home, the devices and the questions run on the film's own clock. */}
          <DeskLayer />
          <Sequence
            name="2 meet"
            from={meet.from}
            durationInFrames={meet.duration}
            premountFor={FPS}
          >
            <Meet />
          </Sequence>
          <Window />
          <Sequence
            name="phone"
            from={PHONE_FROM}
            durationInFrames={close.from + LAST_SWEEP - PHONE_FROM}
            premountFor={FPS}
          >
            <PhoneLayer from={PHONE_FROM} />
          </Sequence>
          <DeskOnPhone />
          {ANSWERS.map(([id, picture, lead]) => (
            <Sequence
              key={id}
              name={id}
              from={shot(id).from - lead}
              durationInFrames={shot(id).duration + lead}
              premountFor={FPS}
            >
              {picture}
            </Sequence>
          ))}
          <Questions />
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
        <SweepLine since={frame - close.from} length={LAST_SWEEP} />
        <Grain />
      </AbsoluteFill>
    </AssetsProvider>
  );
};
