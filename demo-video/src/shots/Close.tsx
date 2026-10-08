import { AbsoluteFill } from "remotion";
import { C, FEATURES, FONT, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { COPY, tween } from "../timing";
import { END_LINE, Headline, Rise } from "../Type";

/** When the mark is whole: the radar line uncovers a finished card. */
export const MARK = 6;

/**
 * The mark in the middle, about 300 pixels across, its centre a little above the
 * frame's. The camera moves in slowly, so the held card is never still.
 */
const cameraAt = (frame: number): View => {
  const z = 14.6 - tween(frame, 0, 60, 0, 0.5, (t) => t);
  return { position: [0.12, -1.1, z], target: [0.12, -1.1, 0] };
};

/**
 * Shot 10, the end card, the one thing in the film that is centred and stays so: the
 * mark, the name, and what RADAR is. It is whole from its first frame, so the radar
 * line uncovers it finished and it is held for the rest of the film.
 */
export const Close: React.FC = () => {
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={C.accent}
        camera={cameraAt}
        style={{ filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})` }}
      >
        <Mark ring={1} line={1} dot={1} />
      </Stage>
      <AbsoluteFill style={{ alignItems: "center", top: 572 }}>
        <Headline lines={[COPY.close.name]} at={-20} />
        {/* The one line in the film at this size. */}
        <div
          style={{
            marginTop: 10,
            fontFamily: FONT,
            fontFeatureSettings: FEATURES,
            fontSize: END_LINE,
            fontWeight: 600,
            letterSpacing: "-0.03em",
            lineHeight: 1.1,
            whiteSpace: "nowrap",
            color: C.ink,
          }}
        >
          <Rise at={-20}>{COPY.close.last}</Rise>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
