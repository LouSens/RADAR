import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Grain } from "./Grain";
import { Ground } from "./Ground";
import { PINGS, Questions } from "./Questions";
import { Close } from "./shots/Close";
import { Meet } from "./shots/Meet";
import { Question } from "./shots/Question";
import { Range } from "./shots/Range";
import { Risk } from "./shots/Risk";
import { Sound } from "./Sound";
import { SweepLine, Swept } from "./Sweep";
import { AssetsProvider, useAssets } from "./three/assets";
import { FPS, shot } from "./timing";
import { World } from "./World";

/**
 * The reel: one situation, answered by the app. Bitcoin falls (shot 1); the mark is
 * drawn and turns out to be the logo of the app (shot 2); then the film stays inside
 * the app, which is one world (World) with the questions over it (Questions), until the
 * radar line uncovers the end card. The start and length of every shot are in
 * shots.json and nowhere else.
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
        <Sound />
        <Swept since={frame - close.from} side="out">
          <Sequence
            name="1 question"
            from={question.from}
            durationInFrames={question.duration}
            premountFor={FPS}
          >
            <Question />
          </Sequence>
          {/* The app and the questions run on the film's own clock, not a shot's. */}
          <World pings={PINGS} />
          <Sequence
            name="2 meet"
            from={meet.from}
            durationInFrames={meet.duration}
            premountFor={FPS}
          >
            <Meet />
          </Sequence>
          {(["range", "risk"] as const).map((id) => (
            <Sequence
              key={id}
              name={id}
              from={shot(id).from}
              durationInFrames={shot(id).duration}
              premountFor={FPS}
            >
              {id === "range" ? <Range /> : <Risk />}
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
          <Swept since={frame - close.from} side="in">
            <Close />
          </Swept>
        </Sequence>
        <SweepLine since={frame - close.from} />
        <Grain />
      </AbsoluteFill>
    </AssetsProvider>
  );
};
