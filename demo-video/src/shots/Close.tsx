import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { BEAT, COPY, EASE_IN_OUT, tween } from "../timing";
import { Headline, LINE, MARGIN, TOP } from "../Type";

/** When the three phrases leave, together; the last line starts as they go. */
const LEAVE = 52;
/** When the mark starts to draw itself, in the space the phrases left. */
const MARK = 58;

/**
 * The mark sits at the left margin above the last line: the camera is off to its right,
 * so it falls left of the middle of the frame, and moves in slowly so that the held
 * picture is never still.
 */
const cameraAt = (frame: number): View => {
  const z = 11.9 - tween(frame, MARK, 150, 0, 0.8, (t) => t);
  return { position: [3.45, -1.25, z], target: [3.45, -1.25, 0] };
};

/**
 * Shot 8. What is yours, a phrase a beat; then the phrases leave together and the mark
 * draws itself over the last line, which is held.
 */
export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const ring = tween(frame, MARK, MARK + 12, 0, 1, EASE_IN_OUT);
  const line = tween(frame, MARK + 6, MARK + 17, 0, 1, EASE_IN_OUT);
  const dot = spring({
    frame: frame - MARK - 15,
    fps,
    config: { damping: 9, mass: 0.45, stiffness: 170 },
  });

  return (
    <AbsoluteFill>
      <Headline
        lines={COPY.close.lines}
        // The first word is already most of the way up on the shot's first frame.
        at={-5}
        lineAt={[-5, BEAT, BEAT * 2]}
        out={LEAVE}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />
      <Stage
        room={assets.room}
        light={C.accent}
        camera={cameraAt}
        style={{ filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})` }}
      >
        <Mark ring={ring} line={line} dot={dot} />
      </Stage>
      <Headline
        lines={COPY.close.last}
        at={LEAVE}
        style={{ position: "absolute", left: MARGIN, top: TOP + LINE * 3 + 56 }}
      />
    </AbsoluteFill>
  );
};
