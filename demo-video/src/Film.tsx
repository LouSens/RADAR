import { Series, useVideoConfig } from "remotion";
import { SHOTS } from "./timing";
import { ShotLayer } from "./ShotLayer";

/**
 * The film: nine shots in order, cuts only. Each shot is its own node so that it can be
 * selected and retimed alone, and takes its length from shots.json.
 */
export const Film: React.FC = () => {
  const { fps } = useVideoConfig();

  return (
    <Series>
      <Series.Sequence
        name="1 Confidence"
        durationInFrames={SHOTS.shot1.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot1" />
      </Series.Sequence>
      <Series.Sequence
        name="2 The hero test"
        durationInFrames={SHOTS.shot2.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot2" />
      </Series.Sequence>
      <Series.Sequence
        name="3 The rhythm"
        durationInFrames={SHOTS.shot3.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot3" />
      </Series.Sequence>
      <Series.Sequence
        name="4 Silence"
        durationInFrames={SHOTS.shot4.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot4" />
      </Series.Sequence>
      <Series.Sequence
        name="5 The turn"
        durationInFrames={SHOTS.shot5.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot5" />
      </Series.Sequence>
      <Series.Sequence
        name="6 The second measurement"
        durationInFrames={SHOTS.shot6.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot6" />
      </Series.Sequence>
      <Series.Sequence
        name="7 Many outcomes"
        durationInFrames={SHOTS.shot7.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot7" />
      </Series.Sequence>
      <Series.Sequence
        name="8 One ball"
        durationInFrames={SHOTS.shot8.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot8" />
      </Series.Sequence>
      <Series.Sequence
        name="9 The name"
        durationInFrames={SHOTS.shot9.frames}
        premountFor={fps}
      >
        <ShotLayer id="shot9" />
      </Series.Sequence>
    </Series>
  );
};
