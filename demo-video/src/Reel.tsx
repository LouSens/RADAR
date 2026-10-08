import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import market from "./fixtures/market.json";
import { Ground } from "./Ground";
import { Empty } from "./shots/Empty";
import { Meet } from "./shots/Meet";
import { Phone } from "./shots/Phone";
import { Range } from "./shots/Range";
import { SweepLine, Swept } from "./Sweep";
import { AssetsProvider, useAssets } from "./three/assets";
import { BEAT, COPY, FPS, SHOTS, SWEEP, type ShotId } from "./timing";

const title = (word: string): string =>
  `${word.charAt(0).toUpperCase()}${word.slice(1)}.`;

/** What each shot draws. A shot not built yet shows its words alone. */
const PICTURE: Readonly<Record<ShotId, React.ReactNode>> = {
  question: <Empty lines={COPY.question} />,
  meet: <Meet />,
  phone: <Phone />,
  // The three states as they stand in the fixture.
  cards: (
    <Empty lines={[market.markets.map((m) => title(m.state)).join(" ")]} />
  ),
  range: <Range />,
  // Provisional: these two figures will follow the example portfolio's fixture.
  risk: <Empty lines={["8% of your money.", "62% of your risk."]} />,
  plan: <Empty lines={COPY.plan} />,
  refusals: (
    <Empty lines={[...COPY.refusals, COPY.signoff.join(" ")]} step={BEAT} />
  ),
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
