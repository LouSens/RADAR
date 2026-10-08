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
import { Model, useObjects, type Objects } from "./three/Model";
import { Screen, useScreens, type Screens } from "./three/Screen";
import { FLOOR, Studio } from "./three/Studio";
import { BEATS } from "./timing";
import { Words } from "./Words";

const OBJECTS = ["cash", "bitcoin", "gold", "stocks", "phone", "logo"] as const;
const SCREENS = ["markets"] as const;
const CLAMP = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const COIN = 0.04; // a coin's radius, so it stands on the floor
const TIPS = BEATS.beat2.from;
const MEET = BEATS.beat3.from;

/** A swell that rises and falls around `centre`: one token making its pitch. */
const pitch = (frame: number, centre: number): number =>
  Math.exp(-((frame - centre) ** 2) / (2 * 8 ** 2));

/**
 * Beats 1 to 3 as one continuous scene. Money arrives; three things circle it, each
 * pushing forward in turn; they scatter, the mark arrives, and the phone comes up
 * showing the app itself.
 */
const Scene: React.FC<{
  readonly objects: Objects;
  readonly screens: Screens;
  readonly onReady: () => void;
}> = ({ objects, screens, onReady }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Beat 1. The cash coin drops, bounces twice and spins to face us.
  const seconds = frame / fps;
  const bounce =
    0.5 * Math.abs(Math.cos(seconds * 5.2)) * Math.exp(-seconds * 3.2);
  const spin = interpolate(frame, [0, 58], [Math.PI * 5, 0], {
    ...CLAMP,
    easing: Easing.out(Easing.cubic),
  });

  // Beat 2. Three tokens fly in and circle the coin, tumbling, each surging in turn.
  const turn = (frame - TIPS) * 0.034;
  const scatter = spring({
    frame: frame - MEET + 8,
    fps,
    config: { damping: 200 },
    durationInFrames: 16,
  });
  const circling = (index: number, delay: number, surge: number) => {
    const arrive = spring({
      frame: frame - TIPS - delay,
      fps,
      config: { damping: 15, mass: 0.8 },
    });
    const angle = turn + (index * Math.PI * 2) / 3 + 0.5;
    const radius =
      (interpolate(arrive, [0, 1], [1.1, 0.25]) - surge * 0.09) *
      (1 + scatter * 4);
    return {
      position: [
        Math.cos(angle) * radius,
        FLOOR +
          COIN +
          0.07 +
          Math.sin(angle * 1.4 + index) * 0.035 +
          surge * 0.02,
        Math.sin(angle) * radius * 0.55 + surge * 0.1,
      ] as const,
      rotation: [
        Math.sin(turn * 1.3 + index) * 0.35,
        -angle * 1.6 + index,
        Math.cos(turn + index) * 0.22,
      ] as const,
      // Nothing is in the room before its cue.
      scale: frame < TIPS + delay ? 0 : (1 + surge * 0.42) * (1 - scatter),
    };
  };
  const bitcoin = circling(0, 0, pitch(frame, TIPS + 44));
  const gold = circling(1, 7, pitch(frame, TIPS + 66));
  const stocks = circling(2, 14, pitch(frame, TIPS + 88));

  // Beat 3. The mark arrives large; then the phone rises with the app on its screen
  // and the mark hands over to it.
  const mark = spring({
    frame: frame - MEET - 4,
    fps,
    config: { damping: 12, mass: 0.7 },
  });
  const rise = spring({
    frame: frame - MEET - 34,
    fps,
    config: { damping: 16, mass: 0.6, stiffness: 150 },
  });

  return (
    <>
      <Studio onReady={onReady} />
      <Model
        object={objects.cash}
        position={[
          0,
          FLOOR + COIN + bounce + scatter * 0.9,
          0.02 - scatter * 0.6,
        ]}
        rotation={[0, spin + (frame > TIPS ? Math.sin(turn * 2) * 0.25 : 0), 0]}
        scale={1.15 * (1 - scatter)}
      />
      <Model object={objects.bitcoin} {...bitcoin} />
      <Model object={objects.gold} {...gold} />
      <Model object={objects.stocks} {...stocks} />
      <Model
        object={objects.phone}
        position={[0, interpolate(rise, [0, 1], [-0.9, -0.1]), 0]}
        rotation={[
          interpolate(rise, [0, 1], [-1.0, -0.04]),
          interpolate(rise, [0, 1], [1.2, -0.2]),
          0,
        ]}
        scale={2.6}
      >
        <Screen texture={screens.markets} />
      </Model>
      <Model
        object={objects.logo}
        position={[0, 0.0 + rise * 0.1, 0.12]}
        rotation={[0, (1 - Math.min(mark, 1)) * -2.2 + rise * 1.6, 0]}
        scale={Math.max(mark, 0) * 1.9 * (1 - Math.min(rise * 1.4, 1))}
      />
    </>
  );
};

export const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const objects = useObjects(OBJECTS);
  const screens = useScreens(SCREENS);
  // Held outside the canvas: a hold placed inside it comes too late.
  const [hold] = useState(() => delayRender("Lighting the scene"));
  const lit = useCallback(() => continueRender(hold), [hold]);
  if (!objects || !screens) {
    return null;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#f4f6f8" }}>
      <AbsoluteFill
        style={{
          // The brand colour blooms behind the phone as RADAR arrives.
          backgroundImage:
            "radial-gradient(1000px 760px at 50% 62%, rgba(98, 207, 232, 0.6), rgba(98, 207, 232, 0) 70%)",
          opacity: interpolate(frame, [MEET, MEET + 60], [0, 1], CLAMP),
        }}
      />
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
            interpolate(frame, [0, 300], [0.05, 0.03], CLAMP),
            interpolate(frame, [0, 300], [1.0, 0.92], CLAMP),
          ],
        }}
      >
        <Scene objects={objects} screens={screens} onReady={lit} />
      </ThreeCanvas>
      <Words text="Payday." from={10} to={52} size={190} top={150} />
      <Words text="Now what?" from={50} to={92} size={190} top={150} />
      <Words
        text="Everyone has a *tip."
        from={TIPS + 6}
        to={MEET - 2}
        size={150}
        top={120}
      />
      <Words
        text="Meet *RADAR."
        from={MEET + 6}
        to={MEET + 42}
        size={200}
        top={110}
      />
      <Words
        text="It starts with what you already own."
        from={MEET + 46}
        to={MEET + 130}
        size={74}
        top={84}
        stagger={3}
        weight={500}
      />
    </AbsoluteFill>
  );
};
