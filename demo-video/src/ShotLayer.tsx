import { AbsoluteFill } from "remotion";
import { COPY, type ShotId } from "./timing";
import { Super } from "./Super";

/**
 * One shot of the film. For now only its place in the edit and its line of copy: the
 * picture is composed here from Blender-made assets, shot by shot, as each is staged
 * (docs/DEMO_STAGING.md).
 */
export const ShotLayer: React.FC<{ readonly id: ShotId }> = ({ id }) => {
  const copy = COPY[id];

  return (
    <AbsoluteFill style={{ backgroundColor: "#14161b" }}>
      {copy ? <Super text={copy.text} from={copy.from} to={copy.to} /> : null}
    </AbsoluteFill>
  );
};
