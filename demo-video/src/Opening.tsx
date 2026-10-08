import { ThreeCanvas } from "@remotion/three";
import { useCallback, useState } from "react";
import {
  AbsoluteFill,
  continueRender,
  delayRender,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Super } from "./Super";
import { Model, useObjects, type Objects } from "./three/Model";
import { FLOOR, Studio } from "./three/Studio";
import { BEATS, COPY, type BeatId } from "./timing";

const OBJECTS = ["cash", "bitcoin", "gold", "stocks", "phone", "logo"] as const;
const CLAMP = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const COIN = 0.04; // a coin's radius, so it stands on the floor
const TIPS = BEATS.beat2.from;
const STOP = BEATS.beat3.from;

/** A swell that rises and falls around `centre`: one token making its pitch. */
const pitch = (frame: number, centre: number): number =>
  Math.exp(-((frame - centre) ** 2) / (2 * 9 ** 2));

/**
 * Beats 1 to 3 as one continuous scene. Money arrives; three things pull at it; then
 * everything stops and the phone comes up.
 */
const Scene: React.FC<{
  readonly objects: Objects;
  readonly onReady: () => void;
}> = ({ objects, onReady }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Beat 1. The cash coin drops, bounces twice and spins to face us.
  const seconds = frame / fps;
  const bounce =
    0.46 * Math.abs(Math.cos(seconds * 5.2)) * Math.exp(-seconds * 3.2);
  const spin = interpolate(frame, [0, 62], [Math.PI * 5, 0], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });

  // Beat 2. Each token arrives, then swells in turn; the coin leans away from each.
  const arrive = (delay: number) =>
    spring({
      frame: frame - TIPS - delay,
      fps,
      config: { damping: 14, mass: 0.7 },
    });
  const bitcoin = pitch(frame, TIPS + 42);
  const gold = pitch(frame, TIPS + 66);
  const stocks = pitch(frame, TIPS + 90);

  // Beat 3. Everything stops; the tokens fall back and the phone rises.
  const still = spring({ frame: frame - STOP, fps, config: { damping: 200 } });
  const rise = spring({
    frame: frame - STOP - 8,
    fps,
    config: { damping: 16, mass: 0.9 },
  });
  const wake = spring({
    frame: frame - STOP - 38,
    fps,
    config: { damping: 11, mass: 0.6 },
  });

  const pulled = (bitcoin * 0.05 - gold * 0.05) * (1 - still);
  const back = -0.42 * still;

  return (
    <>
      <Studio onReady={onReady} />
      <Model
        object={objects.cash}
        position={[
          pulled + 0.26 * still,
          FLOOR + COIN + bounce - stocks * 0.012 * (1 - still),
          0.02 - 0.2 * still,
        ]}
        rotation={[0, spin + pulled * 6 - 0.5 * still, -pulled * 2.2]}
        scale={1 - 0.12 * still}
      />
      <Model
        object={objects.bitcoin}
        position={[
          interpolate(arrive(2), [0, 1], [-0.75, -0.2]) + bitcoin * 0.07,
          FLOOR + COIN + bitcoin * 0.012,
          -0.02 + bitcoin * 0.09 + back,
        ]}
        rotation={[0, 0.42 - bitcoin * 0.3, 0]}
        scale={1 + bitcoin * 0.34}
      />
      <Model
        object={objects.gold}
        position={[
          interpolate(arrive(10), [0, 1], [0.8, 0.21]) - gold * 0.07,
          FLOOR + gold * 0.012,
          -0.01 + gold * 0.09 + back,
        ]}
        rotation={[0, -0.5 + gold * 0.25, 0]}
        scale={1 + gold * 0.3}
      />
      <Model
        object={objects.stocks}
        position={[
          0.015,
          interpolate(arrive(18), [0, 1], [0.6, FLOOR + COIN + 0.105]) +
            stocks * 0.02,
          -0.17 + stocks * 0.15 + back * 0.8,
        ]}
        rotation={[0, -0.12, 0]}
        scale={1.05 + stocks * 0.34}
      />
      <Model
        object={objects.phone}
        position={[0, interpolate(rise, [0, 1], [-0.62, 0.035]), 0.06]}
        rotation={[
          interpolate(rise, [0, 1], [-0.9, -0.06]),
          interpolate(rise, [0, 1], [0.9, -0.16]),
          0,
        ]}
        scale={1.45}
      />
      <Model
        object={objects.logo}
        position={[-0.004, 0.04, 0.085]}
        rotation={[-0.06, -0.16 + (1 - wake) * 1.4, 0]}
        scale={0.62 * Math.max(wake, 0)}
      />
    </>
  );
};

const copyOf = (id: BeatId) => ({
  text: COPY[id].text,
  from: BEATS[id].from + COPY[id].from,
  to: BEATS[id].from + COPY[id].to,
});

export const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const objects = useObjects(OBJECTS);
  // Held outside the canvas: a hold placed inside it comes too late.
  const [hold] = useState(() => delayRender("Lighting the scene"));
  const lit = useCallback(() => continueRender(hold), [hold]);
  if (!objects) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#090a0e",
        backgroundImage:
          "radial-gradient(1300px 900px at 22% -8%, rgba(98, 207, 232, 0.17), transparent 68%), radial-gradient(900px 500px at 50% 78%, rgba(255, 255, 255, 0.05), transparent 70%)",
      }}
    >
      <ThreeCanvas
        width={width}
        height={height}
        shadows
        camera={{
          fov: 26,
          near: 0.05,
          far: 20,
          position: [
            0,
            interpolate(frame, [0, 300], [0.035, 0.05], CLAMP),
            interpolate(frame, [0, 300], [0.76, 0.68], CLAMP),
          ],
        }}
      >
        <Scene objects={objects} onReady={lit} />
      </ThreeCanvas>
      <Super {...copyOf("beat1")} />
      <Super {...copyOf("beat2")} />
      <Super {...copyOf("beat3")} />
    </AbsoluteFill>
  );
};
