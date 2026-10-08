import { Composition } from "remotion";
import { Capture } from "./Capture";
import { Reel } from "./Reel";
import { Home } from "./ui/Home";
import { FPS, HEIGHT, TOTAL, WIDTH } from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Reel"
        component={Reel}
        durationInFrames={TOTAL}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
      <Composition
        id="Home"
        component={Home}
        durationInFrames={1}
        fps={FPS}
        width={390}
        height={844}
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
