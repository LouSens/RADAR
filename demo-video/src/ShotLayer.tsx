import { Video } from "@remotion/media";
import { AbsoluteFill, staticFile } from "remotion";
import { COPY, plateOf, type ShotId } from "./timing";
import { Super } from "./Super";

/**
 * One shot of the film: its rendered plate, and its line of copy if it has one.
 * The plate is picture only. Sound is laid on the film's own timeline.
 */
export const ShotLayer: React.FC<{ readonly id: ShotId }> = ({ id }) => {
  const copy = COPY[id];

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <Video
        src={staticFile(plateOf(id))}
        muted
        objectFit="cover"
        style={{ position: "absolute", width: "100%", height: "100%" }}
      />
      {copy ? <Super text={copy.text} from={copy.from} to={copy.to} /> : null}
    </AbsoluteFill>
  );
};
