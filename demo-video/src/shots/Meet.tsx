import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { LOGO, MARK_ON_SCREEN, REVEAL, onScreen } from "../World";

/** The mark in the middle of the frame, about 300 pixels across. */
const camera = (): View => ({
  position: [0.12, -0.9, 14.6],
  target: [0.12, -0.9, 0],
});

/**
 * Shot 2. The mark draws itself, ring then line then dot. Then the camera pulls back,
 * and the mark is the logo at the top of the app's sidebar: it shrinks on to the logo of
 * the page behind it and hands over to it.
 */
export const Meet: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const film = shot("meet").from + frame;

  const ring = tween(frame, 8, 27, 0, 1, EASE_IN_OUT);
  const line = tween(frame, 21, 36, 0, 1, EASE_IN_OUT);
  const dot = spring({
    frame: frame - 34,
    fps,
    config: { damping: 9, mass: 0.45, stiffness: 170 },
  });
  // The mark turns to face us as it is drawn.
  const turned = tween(frame, 4, 40, 1, 0, EASE);

  // Follow Home's logo as the camera pulls back: the mark stays exactly over it.
  const logo = onScreen(film, "home", LOGO.x, LOGO.y);
  const k = logo ? (logo.s * LOGO.size) / MARK_ON_SCREEN.size : 1;
  const at = logo ?? MARK_ON_SCREEN;
  // It has handed over before the pane starts to turn.
  const gone = tween(film, REVEAL[0] + 8, REVEAL[0] + 18, 0, 1, (t) => t);
  if (gone >= 1) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        transformOrigin: "0 0",
        transform: `translate(${at.x - MARK_ON_SCREEN.x * k}px, ${at.y - MARK_ON_SCREEN.y * k}px) scale(${k})`,
        opacity: 1 - gone,
      }}
    >
      <Stage
        room={assets.room}
        light={lightAt(film)}
        camera={camera}
        style={{
          filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})`,
        }}
      >
        <group rotation={[turned * 0.3, turned * -0.75, turned * 0.08]}>
          <Mark ring={ring} line={line} dot={dot} />
        </group>
      </Stage>
    </AbsoluteFill>
  );
};
