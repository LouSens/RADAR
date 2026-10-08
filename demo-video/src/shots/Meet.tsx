import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Mark, RING } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { COPY, EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { Words } from "../Words";

/** How far above the middle the mark sits, leaving room for the line of type below. */
const LIFT = 0.5;
/** A clear way through the ring: inside it, and to one side of the rising line. */
const GAP = [RING.centre.x - 0.34, RING.centre.y + 0.44 + LIFT] as const;
/** When the camera sets off for the ring, and the shot's last frame, when it is through. */
const PUSH = [46, 59] as const;

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/**
 * The camera drifts in while the mark is drawn, then goes through the ring: slowly at
 * first, so the ring is seen to grow and its edge to pass the lens, and through it on the
 * shot's last frame.
 */
const cameraAt = (frame: number): View => {
  const drift = tween(frame, 0, PUSH[0], 0, 1, (t) => t);
  const push = tween(frame, PUSH[0], PUSH[1], 0, 1, (t) => t ** 1.6);
  const x = mix(0, GAP[0], Math.min(push * 2, 1));
  const y = mix(0, GAP[1], Math.min(push * 2, 1));
  return {
    position: [x, y, mix(mix(11.8, 10.6, drift), -0.7, push)],
    target: [x, y, -8],
  };
};

/**
 * Shot 2. The mark draws itself, ring then line then dot, and the camera goes through
 * the ring.
 */
export const Meet: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
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
  const pushing = frame >= PUSH[0];

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={lightAt(shot("meet").from + frame)}
        camera={cameraAt}
        shutter={pushing ? 0.65 : 0}
        style={{
          filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})`,
        }}
      >
        <group
          position={[0, LIFT, 0]}
          rotation={[turned * 0.3, turned * -0.75, turned * 0.08]}
        >
          <Mark ring={ring} line={line} dot={dot} />
        </group>
      </Stage>
      <AbsoluteFill style={{ alignItems: "center", top: 770 }}>
        <Words text={COPY.meet[0]} at={22} out={46} size={132} stagger={5} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
