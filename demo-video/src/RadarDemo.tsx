import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { useVideoConfig } from "remotion";
import { Account } from "./scenes/Account";
import { Futures } from "./scenes/Futures";
import { Hook } from "./scenes/Hook";
import { Ladder } from "./scenes/Ladder";
import { Noise } from "./scenes/Noise";
import { Proof } from "./scenes/Proof";
import { Reveal } from "./scenes/Reveal";

/** The whole film: docs/DEMO_STORYBOARD.md, scene by scene. */
export const RadarDemo: React.FC = () => {
  const { fps } = useVideoConfig();

  return (
    <TransitionSeries>
      <TransitionSeries.Sequence
        name="1 Hook"
        durationInFrames={150}
        premountFor={fps}
      >
        <Hook />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="2 Noise"
        durationInFrames={150}
        premountFor={fps}
      >
        <Noise />
      </TransitionSeries.Sequence>
      {/* A hard cut: the noise stops dead and the name appears. */}
      <TransitionSeries.Sequence
        name="3 Reveal"
        durationInFrames={150}
        premountFor={fps}
      >
        <Reveal line="The analyst that never trades." />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="4 Account"
        durationInFrames={230}
        premountFor={fps}
      >
        <Account />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="5 Ladder"
        durationInFrames={230}
        premountFor={fps}
      >
        <Ladder />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="6 Futures"
        durationInFrames={230}
        premountFor={fps}
      >
        <Futures />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="7 Proof"
        durationInFrames={150}
        premountFor={fps}
      >
        <Proof />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={fade()}
        timing={linearTiming({ durationInFrames: 12 })}
      />
      <TransitionSeries.Sequence
        name="8 Close"
        durationInFrames={162}
        premountFor={fps}
      >
        <Reveal
          line="You decide. RADAR shows you what is true."
          address="github.com/LouSens/RADAR"
        />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
