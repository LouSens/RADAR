import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, FEATURES, FONT, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { BEAT, COPY, EASE_IN_OUT, tween } from "../timing";
import { END_LINE, Headline, MARGIN, Rise, TOP } from "../Type";

/** When each phrase starts, when all three leave, and when the mark arrives. */
export const PHRASES = [0, BEAT, BEAT * 2] as const;
const LEAVE = 44;
export const MARK = 50;

/**
 * The mark in the middle, about 300 pixels across, its centre a little above the
 * frame's. The camera moves in slowly, so the held card is never still.
 */
const cameraAt = (frame: number): View => {
  const z = 14.6 - tween(frame, MARK, 110, 0, 0.7, (t) => t);
  return { position: [0.12, -1.1, z], target: [0.12, -1.1, 0] };
};

/**
 * Shot 8. What is yours, a phrase a beat, on the grid; then the phrases leave together
 * and the end card arrives in the middle, the one thing in the film that is centred: the
 * mark, the name, and what RADAR is.
 */
export const Close: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  // The ring starts round as the phrases leave, so the frame is never empty between
  // them; the line and the dot land with the mark's beat.
  const ring = tween(frame, LEAVE, MARK + 3, 0, 1, EASE_IN_OUT);
  const line = tween(frame, MARK, MARK + 9, 0, 1, EASE_IN_OUT);
  const dot = spring({
    frame: frame - MARK - 7,
    fps,
    config: { damping: 9, mass: 0.45, stiffness: 170 },
  });

  return (
    <AbsoluteFill>
      <Headline
        lines={COPY.close.lines}
        // The first word is already most of the way up on the shot's first frame.
        at={-5}
        lineAt={[-5, PHRASES[1], PHRASES[2]]}
        // The two words of a phrase come close together, so that the third phrase is
        // whole before all three leave for the mark.
        step={3}
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
      <AbsoluteFill style={{ alignItems: "center", top: 572 }}>
        <Headline lines={COPY.close.name} at={MARK + 2} />
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
          <Rise at={MARK + 6}>{COPY.close.last}</Rise>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
