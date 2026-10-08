import { Composition } from "remotion";
import { Capture } from "./Capture";
import { Film } from "./Film";
import { FPS, FRAMES, HEIGHT, WIDTH } from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Film"
        component={Film}
        durationInFrames={FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
      <Composition
        id="Capture"
        component={Capture}
        durationInFrames={1}
        fps={30}
        width={390}
        height={844}
        defaultProps={{ path: "markets" }}
      />
    </>
  );
};
