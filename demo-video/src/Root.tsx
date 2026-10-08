import { Composition, Folder } from "remotion";
import { RadarDemo } from "./RadarDemo";
import { Account } from "./scenes/Account";
import { Futures } from "./scenes/Futures";
import { Hook } from "./scenes/Hook";
import { Ladder } from "./scenes/Ladder";
import { Noise } from "./scenes/Noise";
import { Proof } from "./scenes/Proof";
import { Reveal } from "./scenes/Reveal";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* 150 + 150 + 150 + 230 + 230 + 230 + 150 + 162, less six 12-frame fades. */}
      <Composition
        id="RadarDemo"
        component={RadarDemo}
        durationInFrames={1380}
        fps={30}
        width={1920}
        height={1080}
      />
      <Folder name="Scenes">
        <Composition
          id="Hook"
          component={Hook}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Noise"
          component={Noise}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Reveal"
          component={Reveal}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ line: "The analyst that never trades." }}
        />
        <Composition
          id="Account"
          component={Account}
          durationInFrames={230}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Ladder"
          component={Ladder}
          durationInFrames={230}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Futures"
          component={Futures}
          durationInFrames={230}
          fps={30}
          width={1920}
          height={1080}
        />
        <Composition
          id="Proof"
          component={Proof}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
        />
      </Folder>
    </>
  );
};
