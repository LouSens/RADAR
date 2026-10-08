import { AbsoluteFill, Series, useVideoConfig } from "remotion";
import { Opening } from "./Opening";
import { Super } from "./Super";
import { BEATS, COPY, type BeatId } from "./timing";

/** A beat that is written but not yet built: its line over the app's dark ground. */
const Pending: React.FC<{ readonly id: BeatId }> = ({ id }) => (
  <AbsoluteFill style={{ backgroundColor: "#090a0e" }}>
    <Super text={COPY[id].text} from={COPY[id].from} to={COPY[id].to} />
  </AbsoluteFill>
);

/** The film, "Payday": seven beats, thirty seconds. Beats 1 to 3 are one scene. */
export const Film: React.FC = () => {
  const { fps } = useVideoConfig();

  return (
    <Series>
      <Series.Sequence
        name="1 to 3 Payday, tips, what you own"
        durationInFrames={BEATS.beat4.from}
        premountFor={fps}
      >
        <Opening />
      </Series.Sequence>
      <Series.Sequence
        name="4 Where your money sits"
        durationInFrames={BEATS.beat4.frames}
        premountFor={fps}
      >
        <Pending id="beat4" />
      </Series.Sequence>
      <Series.Sequence
        name="5 Where your risk sits"
        durationInFrames={BEATS.beat5.frames}
        premountFor={fps}
      >
        <Pending id="beat5" />
      </Series.Sequence>
      <Series.Sequence
        name="6 This month's money"
        durationInFrames={BEATS.beat6.frames}
        premountFor={fps}
      >
        <Pending id="beat6" />
      </Series.Sequence>
      <Series.Sequence
        name="7 The name"
        durationInFrames={BEATS.beat7.frames}
        premountFor={fps}
      >
        <Pending id="beat7" />
      </Series.Sequence>
    </Series>
  );
};
