import { Composition } from "remotion";
import { Capture } from "./Capture";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Capture"
      component={Capture}
      durationInFrames={1}
      fps={30}
      width={390}
      height={844}
      defaultProps={{ path: "markets" }}
    />
  );
};
