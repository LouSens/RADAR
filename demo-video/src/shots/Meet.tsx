import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { LANDED } from "../DeskLayer";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Mark, RING } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { EASE_IN_OUT, HEIGHT, shot, tween } from "../timing";
import { AT as HOME, DESK } from "../ui/Desk";
import { GIVES, RESTS } from "./Question";

const FOV = 28;
/** Pixels to a unit of the scene, for a camera one unit away. */
const PER_UNIT = HEIGHT / 2 / Math.tan((FOV * Math.PI) / 360);
/** Where the camera stands once the mark is drawn: about 300 pixels across. */
const STANDS = { x: 0.12, y: -0.9, z: 14.6 } as const;

interface Circle {
  readonly x: number;
  readonly y: number;
  readonly r: number;
}
/** The ring in the frame for a camera, and the camera that puts the ring on a circle. */
const ringFrom = (at: typeof STANDS): Circle => ({
  x: 960 + ((RING.centre.x - at.x) * PER_UNIT) / at.z,
  y: 540 - ((RING.centre.y - at.y) * PER_UNIT) / at.z,
  r: (RING.radius * PER_UNIT) / at.z,
});
const cameraFor = (ring: Circle): View => {
  const each = ring.r / RING.radius;
  const x = RING.centre.x - (ring.x - 960) / each;
  const y = RING.centre.y + (ring.y - 540) / each;
  return { position: [x, y, PER_UNIT / each], target: [x, y, 0], fov: FOV };
};
const DRAWN_RING = ringFrom(STANDS);

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
/** The ring comes back from the size of the coin to the size the mark is drawn at. */
const SETTLES = [10, 26] as const;
/** The radar's line, turning once inside the ring. */
export const TURNS = [9, 23] as const;
/** When the rising line is drawn, and when the dot lands. */
export const LINE = [22, 34] as const;
export const DOT = 33;
/** When the mark sets off for the sidebar. It has landed at LANDED (DeskLayer). */
export const SHRINKS = LANDED - meet - 18;

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/**
 * Shot 2. The coin's rim is the mark's ring: the ring is there where the coin stood, in
 * the mark's colour, as the coin goes. The radar's line turns once inside it, the
 * rising line is drawn and the dot lands. Then the mark shrinks and lands as the logo
 * at the top of the app's sidebar, and Home builds itself round it (DeskLayer).
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

  const settled = tween(frame, SETTLES[0], SETTLES[1], 0, 1, EASE_IN_OUT);
  const ring: Circle = {
    x: mix(RESTS.x, DRAWN_RING.x, settled),
    y: mix(RESTS.y, DRAWN_RING.y, settled),
    // The coin's rim is a little inside its edge.
    r: mix(RESTS.r * 0.965, DRAWN_RING.r, settled),
  };
  const line = tween(frame, LINE[0], LINE[1], 0, 1, EASE_IN_OUT);
  const dot = spring({
    frame: frame - DOT,
    fps,
    config: { damping: 9, mass: 0.45, stiffness: 170 },
  });

  // One move to the sidebar: it shrinks as it goes, and its centre goes straight there.
  const go = tween(frame, SHRINKS, LANDED - meet, 0, 1, EASE_IN_OUT);
  const k = (LOGO.size / DRAWN.size) ** go;
  const x = DRAWN.x + (LOGO.x - DRAWN.x) * go;
  const y = DRAWN.y + (LOGO.y - DRAWN.y) * go;

  const angle = tween(frame, TURNS[0], TURNS[1], 0, 360, EASE_IN_OUT);
  const turning =
    tween(frame, TURNS[0] - 2, TURNS[0] + 2, 0, 1, (t) => t) *
    (1 - tween(frame, TURNS[1] - 2, TURNS[1] + 5, 0, 1, (t) => t));
  const trail = 90;
  const inside = ring.r * 0.97;

  return (
    <AbsoluteFill
      style={{
        transformOrigin: "0 0",
        transform: `translate(${x - DRAWN.x * k}px, ${y - DRAWN.y * k}px) scale(${k})`,
        opacity: (1 - gone) * tween(frame, 7, GIVES, 0, 1, (t) => t),
      }}
    >
      {/* The radar's line, once round, inside the ring and nowhere else. */}
      {turning > 0 && (
        <div
          style={{
            position: "absolute",
            left: ring.x - inside,
            top: ring.y - inside,
            width: inside * 2,
            height: inside * 2,
            borderRadius: "50%",
            overflow: "hidden",
            opacity: turning,
            background: `conic-gradient(from ${angle - trail}deg, transparent 0deg, ${fade(C.accent, 0.04)} ${trail * 0.4}deg, ${fade(C.accent, 0.4)} ${trail}deg, transparent ${trail}deg)`,
          }}
        >
          <div
            style={{
              position: "absolute",
              left: inside - 2.5,
              top: 0,
              width: 5,
              height: inside,
              transformOrigin: "50% 100%",
              rotate: `${angle}deg`,
              borderRadius: 3,
              background: `linear-gradient(to top, ${C.accent}, ${fade(C.accent, 0.8)})`,
              boxShadow: `0 0 18px 3px ${fade(C.accent, 0.65)}`,
            }}
          />
        </div>
      )}
      <Stage
        room={assets.room}
        light={lightAt(film)}
        camera={() => cameraFor(ring)}
        style={{
          filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})`,
        }}
      >
        <Mark ring={1} line={line} dot={dot} />
      </Stage>
    </AbsoluteFill>
  );
};
