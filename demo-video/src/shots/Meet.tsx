import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { LANDED } from "../DeskLayer";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { AT as HOME, DESK } from "../ui/Desk";

/** The mark in the middle of the frame, about 300 pixels across. */
const camera = (): View => ({
  position: [0.12, -0.9, 14.6],
  target: [0.12, -0.9, 0],
});

/**
 * The mark on screen as it is drawn: the centre and width of the square the app's logo
 * is drawn in, measured from a still.
 */
const DRAWN = { x: 944, y: 404, size: 499 } as const;
/** The logo in Home's sidebar, in the frame: the mark lands exactly on it. */
const LOGO = {
  x: (HOME.side.x + 20 + 15) * DESK.zoom,
  y: (HOME.side.y + 20 + 15) * DESK.zoom,
  size: 30 * DESK.zoom,
} as const;

const meet = shot("meet").from;
/** When the mark sets off for the sidebar. It has landed at LANDED (DeskLayer). */
export const SHRINKS = LANDED - meet - 18;

/**
 * Shot 2. The mark draws itself, ring then line then dot; then it shrinks and lands as
 * the logo at the top of the app's sidebar, and Home builds itself round it (DeskLayer).
 */
export const Meet: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const film = meet + frame;
  const gone = tween(film, LANDED - 3, LANDED + 3, 0, 1, (t) => t);
  if (gone >= 1) {
    return null;
  }

  const ring = tween(frame, 8, 27, 0, 1, EASE_IN_OUT);
  const line = tween(frame, 21, 36, 0, 1, EASE_IN_OUT);
  const dot = spring({
    frame: frame - 34,
    fps,
    config: { damping: 9, mass: 0.45, stiffness: 170 },
  });
  // The mark turns to face us as it is drawn.
  const turned = tween(frame, 4, 40, 1, 0, EASE);

  // One move to the sidebar: it shrinks as it goes, and its centre goes straight there.
  const go = tween(frame, SHRINKS, LANDED - meet, 0, 1, EASE_IN_OUT);
  const k = (LOGO.size / DRAWN.size) ** go;
  const x = DRAWN.x + (LOGO.x - DRAWN.x) * go;
  const y = DRAWN.y + (LOGO.y - DRAWN.y) * go;

  return (
    <AbsoluteFill
      style={{
        transformOrigin: "0 0",
        transform: `translate(${x - DRAWN.x * k}px, ${y - DRAWN.y * k}px) scale(${k})`,
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
