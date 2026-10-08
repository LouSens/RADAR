import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Ground } from "./Ground";
import { Cards } from "./shots/Cards";
import { Close } from "./shots/Close";
import { Meet } from "./shots/Meet";
import { Phone } from "./shots/Phone";
import { Plan } from "./shots/Plan";
import { Question } from "./shots/Question";
import { Range } from "./shots/Range";
import { Risk } from "./shots/Risk";
import { Sound } from "./Sound";
import { SweepLine, Swept } from "./Sweep";
import { AssetsProvider, useAssets } from "./three/assets";
import { FPS, SHOTS, SWEEP, type ShotId } from "./timing";

/** What each shot draws. */
const PICTURE: Readonly<Record<ShotId, React.ReactNode>> = {
  question: <Question />,
  meet: <Meet />,
  phone: <Phone />,
  cards: <Cards />,
  range: <Range />,
  risk: <Risk />,
  plan: <Plan />,
  close: <Close />,
};

/**
 * The reel: one sequence a shot, on one ground whose light changes colour beneath them.
 * A shot marked `sweep` is uncovered by the radar line, and the shot before it stays on
 * until the line has gone round.
 */
export const Reel: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useAssets();

  return (
    <AssetsProvider value={assets}>
      <AbsoluteFill>
        <Ground />
        <Sound />
        {SHOTS.map((shot, i) => {
          const next = SHOTS[i + 1];
          const tail = next?.sweep ? SWEEP : 0;
          let picture = PICTURE[shot.id];
          if (shot.sweep) {
            picture = (
              <Swept since={frame - shot.from} side="in">
                {picture}
              </Swept>
            );
          }
          if (next?.sweep) {
            picture = (
              <Swept since={frame - next.from} side="out">
                {picture}
              </Swept>
            );
          }
          return (
            <Sequence
              key={shot.id}
              name={`${i + 1} ${shot.id}`}
              from={shot.from}
              durationInFrames={shot.duration + tail}
              premountFor={FPS}
            >
              {picture}
            </Sequence>
          );
        })}
        {SHOTS.filter((shot) => shot.sweep).map((shot) => (
          <SweepLine key={shot.id} since={frame - shot.from} />
        ))}
      </AbsoluteFill>
    </AssetsProvider>
  );
};
