import { Composition } from "remotion";
import { Film } from "./Film";
import { FPS, FRAMES, HEIGHT, WIDTH } from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Film"
      component={Film}
      durationInFrames={FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
