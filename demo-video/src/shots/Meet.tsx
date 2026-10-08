import {
  AbsoluteFill,
  Easing,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Mark, RING } from "../three/Mark";
import { Rig, Stage } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { COPY, EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { Words } from "../Words";

/** How far above the middle the mark sits, leaving room for the line of type below. */
const LIFT = 0.5;
/** A clear way through the ring: inside it, and to one side of the rising line. */
const GAP = [RING.centre.x - 0.34, RING.centre.y + 0.44 + LIFT] as const;

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

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
  const drift = tween(frame, 0, 46, 0, 1, (t) => t);
  const push = tween(frame, 40, 59, 0, 1, Easing.in(Easing.cubic));

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={lightAt(shot("meet").from + frame)}
        style={{
          filter: `drop-shadow(0 0 ${26 + push * 60}px ${fade(C.accent, 0.5)})`,
        }}
      >
        <Rig
          position={[
            mix(0, GAP[0], push),
            mix(0, GAP[1], push),
            mix(mix(11.8, 11, drift), -0.9, push),
          ]}
          target={[mix(0, GAP[0], push), mix(0, GAP[1], push), -6]}
        />
        <group
          position={[0, LIFT, 0]}
          rotation={[turned * 0.3, turned * -0.75, turned * 0.08]}
        >
          <Mark ring={ring} line={line} dot={dot} />
        </group>
      </Stage>
      <AbsoluteFill style={{ alignItems: "center", top: 770 }}>
        <Words text={COPY.meet[0]} at={22} out={44} size={132} stagger={5} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
