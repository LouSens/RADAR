import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Scene } from "three";
import { lightAt } from "../Ground";
import { C, fade } from "../theme";
import { Phone as PhoneObject, PHONE } from "../three/Phone";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { COPY, EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { Words } from "../Words";

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;
const RIGHT = Math.PI / 2;

/** The glide along the edge, the swing round to face us, and the slow settle after. */
const GLIDE = [0, 34] as const;
const TURN = [22, 46] as const;
const REST = [42, 90] as const;

/** How the phone is held at a moment of the shot. */
const heldAt = (frame: number) => {
  const turn = tween(frame, TURN[0], TURN[1], 0, 1, EASE_IN_OUT);
  const rest = tween(frame, REST[0], REST[1], 0, 1, EASE);
  return {
    // Lying on its side with its edge to the lens, then up, leaning, and turned a
    // little away: never square to the camera.
    roll: mix(RIGHT, -0.13, turn) + rest * 0.025,
    yaw: mix(-RIGHT * 0.86, -0.46, turn) + rest * 0.13,
    pitch: mix(0.05, -0.07, turn) + rest * 0.02,
  };
};

/**
 * Close on the edge, travelling along it; then back, with the phone large on the left
 * and running off the bottom of the frame.
 */
const cameraAt = (frame: number): View => {
  // The glide never stops dead: it is still moving when the turn takes over.
  const glide = tween(frame, GLIDE[0], GLIDE[1], 0, 1, (t) => t);
  const turn = tween(frame, TURN[0], TURN[1], 0, 1, EASE_IN_OUT);
  const rest = tween(frame, REST[0], REST[1], 0, 1, EASE);
  const edge = PHONE.width / 2;
  const along = mix(-0.5, 0.24, glide);
  return {
    position: [
      mix(along, 0.6, turn),
      mix(0.1, 0.2, turn),
      mix(edge + 0.42, 2.85 - rest * 0.13, turn),
    ],
    target: [
      mix(along + 0.16, 0.6, turn),
      mix(0.065, 0.2, turn),
      mix(edge, 0, turn),
    ],
  };
};

const moveAt = (frame: number, scene: Scene): void => {
  const held = heldAt(frame);
  scene.getObjectByName("phone-roll")?.rotation.set(0, 0, held.roll);
  scene.getObjectByName("phone-turn")?.rotation.set(held.pitch, held.yaw, 0);
  // The three blips go slowly round.
  scene.getObjectByName("orbit")?.rotation.set(0, 0, frame * 0.012);
};

/** What the account holds, as the three colours the app gives them. */
const BLIPS = [
  { colour: C.btc, angle: 1.3, at: 50 },
  { colour: C.gold, angle: -0.3, at: 57 },
  { colour: C.stock, angle: -1.5, at: 64 },
] as const;
const ORBIT = 0.53;

/**
 * Shot 3. Out of the ring: a close glide along the phone's metal edge, then it swings to
 * face us with the app's Home on its screen, and what it holds appears round it.
 */
export const Phone: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }

  const glide = tween(frame, GLIDE[0], GLIDE[1], 0, 1, (t) => t);
  const turn = tween(frame, TURN[0], TURN[1], 0, 1, EASE_IN_OUT);
  const light = lightAt(shot("phone").from + frame);
  const ring = tween(frame, 44, 62, 0, 1, EASE_IN_OUT);
  const moving = frame < TURN[1] + 2;

  return (
    <AbsoluteFill>
      {/* The screen's own light on the air behind it. */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(560px 640px at 500px 660px, ${fade(light, 0.2)}, transparent 72%)`,
          opacity: turn,
        }}
      />
      <Stage
        room={assets.room}
        strength={mix(0.42, 0.62, turn)}
        light={light}
        camera={cameraAt}
        move={moveAt}
        shutter={frame < TURN[0] ? 0.3 : moving ? 0.8 : 0}
        turn={mix(0.6, 2.2, glide) + turn * 0.9}
      >
        <group name="phone-roll">
          <group name="phone-turn">
            <PhoneObject
              object={assets.phone}
              screen={assets.screens.home}
              lit={tween(frame, 14, 32, 0.2, 1)}
            />
          </group>
          {/* A faint ring round the phone, lying almost flat, with a blip for each
              thing the account holds. */}
          <group position={[0, -0.12, 0]} rotation={[RIGHT * 0.84, 0, 0]}>
            <group name="orbit">
              {ring > 0 && (
                <mesh>
                  <torusGeometry
                    args={[ORBIT, 0.0028, 8, 180, ring * Math.PI * 2]}
                  />
                  <meshBasicMaterial
                    color={C.accent}
                    transparent
                    opacity={0.34}
                    toneMapped={false}
                  />
                </mesh>
              )}
              {BLIPS.map((blip) => {
                const on = spring({
                  frame: frame - blip.at,
                  fps,
                  config: { damping: 10, mass: 0.4, stiffness: 180 },
                });
                return (
                  <group
                    key={blip.colour}
                    position={[
                      Math.cos(blip.angle) * ORBIT,
                      Math.sin(blip.angle) * ORBIT,
                      0,
                    ]}
                    scale={Math.max(on, 0.0001)}
                  >
                    <mesh>
                      <sphereGeometry args={[0.026, 24, 16]} />
                      <meshBasicMaterial
                        color={blip.colour}
                        toneMapped={false}
                      />
                    </mesh>
                    <mesh>
                      <sphereGeometry args={[0.06, 24, 16]} />
                      <meshBasicMaterial
                        color={blip.colour}
                        transparent
                        opacity={0.2}
                        depthWrite={false}
                        toneMapped={false}
                      />
                    </mesh>
                  </group>
                );
              })}
            </group>
          </group>
        </group>
      </Stage>
      <AbsoluteFill
        style={{ left: 900, top: 372, gap: 14, flexDirection: "column" }}
      >
        <Words text={COPY.phone[0]} at={42} size={98} />
        <Words text={COPY.phone[1]} at={54} size={98} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
