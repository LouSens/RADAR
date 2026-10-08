import { AbsoluteFill, useCurrentFrame } from "remotion";
import { lightAt } from "../Ground";
import { fade } from "../theme";
import { Phone as PhoneObject, PHONE } from "../three/Phone";
import { Rig, Stage } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { COPY, EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { Words } from "../Words";

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const RIGHT = Math.PI / 2;

/**
 * Shot 3. Out of the ring: a close glide along the phone's metal edge, then it swings to
 * face us with the app on its screen.
 */
export const Phone: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }

  // The glide never stops dead: it is still moving when the turn takes over.
  const glide = tween(frame, 0, 36, 0, 1, (t) => t);
  const turn = tween(frame, 26, 50, 0, 1, EASE_IN_OUT);
  const rest = tween(frame, 46, 90, 0, 1, EASE);
  const light = lightAt(shot("phone").from + frame);

  // Lying on its side with its edge to the lens, then upright and facing us.
  const roll = mix(RIGHT, 0, turn);
  const yaw = mix(-RIGHT * 0.86, -0.3, turn) + rest * 0.14;
  const pitch = mix(0.05, -0.06, turn) + rest * 0.03;

  // Close on the edge, travelling along it; then back, with the phone left of centre.
  const edge = PHONE.width / 2;
  const along = mix(-0.5, 0.28, glide);
  const position = [
    mix(along, 0.72, turn),
    mix(0.1, 0.02, turn),
    mix(edge + 0.42, 3.95 - rest * 0.15, turn),
  ] as const;
  const target = [
    mix(along + 0.16, 0.72, turn),
    mix(0.065, 0, turn),
    mix(edge, 0, turn),
  ] as const;

  return (
    <AbsoluteFill>
      {/* The screen's own light on the air behind it. */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(520px 560px at 560px 540px, ${fade(light, 0.2)}, transparent 72%)`,
          opacity: turn,
        }}
      />
      <Stage
        room={assets.room}
        strength={mix(0.5, 0.8, turn)}
        light={light}
        turn={mix(0.6, 2.2, glide) + turn * 0.9}
      >
        <Rig position={position} target={target} />
        <group rotation={[0, 0, roll]}>
          <group rotation={[pitch, yaw, 0]}>
            <PhoneObject
              object={assets.phone}
              screen={assets.screens.markets}
              lit={tween(frame, 20, 40, 0.25, 1)}
            />
          </group>
        </group>
      </Stage>
      <AbsoluteFill
        style={{ left: 1010, top: 432, gap: 18, flexDirection: "column" }}
      >
        <Words text={COPY.phone[0]} at={46} size={78} />
        <Words text={COPY.phone[1]} at={58} size={78} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
