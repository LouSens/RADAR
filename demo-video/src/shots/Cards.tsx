import { useMemo } from "react";
import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Object3D, PerspectiveCamera, Vector3, type Scene } from "three";
import market from "../fixtures/market.json";
import { lightAt } from "../Ground";
import { fade } from "../theme";
import { Phone as PhoneObject } from "../three/Phone";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import {
  COPY,
  EASE,
  EASE_IN,
  EASE_IN_OUT,
  HEIGHT,
  WIDTH,
  shot,
  tween,
} from "../timing";
import { MarketCard, TONE, TopEdge } from "../ui/kit";
import { Headline, MARGIN, TOP } from "../Type";

const markets = market.markets;
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// ---- The phone the cards leave: its lower half, where Home's three markets are.

const HELD = { roll: -0.08, pitch: -0.04, yaw: -0.3 } as const;
const VIEW: View = { position: [0.52, -0.4, 2.5], target: [0.52, -0.4, 0] };
/** The lit screen in the film's units (blender/build_assets.py) and in the app's pixels. */
const SCREEN = { width: 0.655, height: 1.418, lift: 0.041 } as const;
const PAGE = { width: 390, height: 844 } as const;
/** The three market cards on Home, in the app's pixels: middles, and their width. */
const ON_HOME = { xs: [73, 195, 317], y: 728, width: 114 } as const;

/** Where a point of the phone's screen falls in the frame, and how large a pixel is there. */
const onFrame = (
  appX: number,
  appY: number,
): { readonly x: number; readonly y: number; readonly unit: number } => {
  const roll = new Object3D();
  const turn = new Object3D();
  roll.add(turn);
  roll.rotation.set(0, 0, HELD.roll);
  turn.rotation.set(HELD.pitch, HELD.yaw, 0);
  roll.updateMatrixWorld(true);
  const lens = new PerspectiveCamera(28, WIDTH / HEIGHT, 0.02, 200);
  lens.position.set(...VIEW.position);
  lens.lookAt(...VIEW.target);
  lens.updateMatrixWorld(true);
  const see = (dx: number): Vector3 =>
    turn
      .localToWorld(
        new Vector3(
          ((appX + dx) / PAGE.width - 0.5) * SCREEN.width,
          (0.5 - appY / PAGE.height) * SCREEN.height,
          SCREEN.lift,
        ),
      )
      .project(lens);
  const here = see(0);
  const next = see(1);
  return {
    x: (here.x * 0.5 + 0.5) * WIDTH,
    y: (0.5 - here.y * 0.5) * HEIGHT,
    unit: ((next.x - here.x) * WIDTH) / 2,
  };
};

// ---- The row of panes, in frame pixels: each one further along and further away.

/** How far the viewer is from the picture plane, in pixels. */
const DEPTH = 1500;
const PANE = { width: 780, zoom: 2.85 } as const;
const ROW = { x: 800, z: -560, turn: -24 } as const;
/** The frame each pane is looked at, and how long the camera rests on it. */
const LOOK = [16, 40, 64] as const;
const REST = 13;

/** Where the camera is along the row: it glides from one pane to the next, never still. */
const along = (frame: number): number => {
  const stops = [
    [0, -0.62],
    [LOOK[0], -0.06],
    [LOOK[0] + REST, 0.05],
    [LOOK[1], 0.94],
    [LOOK[1] + REST, 1.05],
    [LOOK[2], 1.94],
    [90, 2.08],
  ] as const;
  for (let i = 1; i < stops.length; i++) {
    const [from, a] = stops[i - 1];
    const [to, b] = stops[i];
    if (frame <= to) {
      const rest = i % 2 === 0;
      return tween(frame, from, to, a, b, rest ? (t) => t : EASE_IN_OUT);
    }
  }
  return stops[stops.length - 1][1];
};

const phoneAt = (frame: number, scene: Scene): void => {
  const leave = tween(frame, 3, 20, 0, 1, EASE_IN);
  const roll = scene.getObjectByName("phone-roll");
  roll?.rotation.set(0, 0, HELD.roll - leave * 0.25);
  roll?.position.set(-leave * 1.5, -leave * 0.35, -leave * 0.9);
  scene
    .getObjectByName("phone-turn")
    ?.rotation.set(HELD.pitch, HELD.yaw - leave * 0.5, 0);
};

/**
 * Shot 4. The three market cards lift off the phone's screen as panes of glass and stand
 * in a row going away from us. The camera travels down the row; each pane's week is drawn
 * and its state named as it is reached. The cards are the app's own, drawn live.
 */
export const Cards: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  // Its own copy: an object can stand in only one scene, and shot 3 has the first.
  const phone = useMemo(() => assets?.phone.clone(), [assets]);
  if (!assets || !phone) {
    return null;
  }
  const light = lightAt(shot("cards").from + frame);
  const where = along(frame);
  const cameraX = where * ROW.x - 40;
  const cameraZ = where * ROW.z;

  return (
    <AbsoluteFill>
      {/* Behind everything: the phone and the panes pass in front of it. The accent
          word takes the colour of the market in view. */}
      <Headline
        lines={COPY.cards}
        at={4}
        accent={light}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />
      <Stage
        room={assets.room}
        strength={0.62}
        light={light}
        camera={() => VIEW}
        move={phoneAt}
        shutter={frame > 3 && frame < 22 ? 0.7 : 0}
        style={{ opacity: 1 - tween(frame, 12, 21, 0, 1) }}
      >
        <group name="phone-roll">
          <group name="phone-turn">
            <PhoneObject object={phone} screen={assets.screens.home} />
          </group>
        </group>
      </Stage>

      <AbsoluteFill
        style={{ perspective: DEPTH, perspectiveOrigin: "66% 60%" }}
      >
        {markets.map((m, i) => {
          const tone = TONE[m.tone];
          // Off the screen: each card starts exactly where it lies on the phone.
          const lift = tween(frame, 1 + i * 2, 18 + i * 2, 0, 1, EASE_IN_OUT);
          const from = onFrame(ON_HOME.xs[i], ON_HOME.y);
          const small = (ON_HOME.width * from.unit) / PANE.width;
          // In the row, as the camera sees it now.
          const dz = i * ROW.z - cameraZ;
          const dx = i * ROW.x - cameraX;
          const seen = DEPTH / (DEPTH - dz);
          const x = mix(from.x, WIDTH / 2 + 310 + dx * seen, lift);
          const y = mix(from.y, HEIGHT * 0.6, lift);
          const size = mix(small, seen, lift);
          const turn = mix(-12, ROW.turn + (where - i) * 9, lift);
          // The pane being looked at is sharp; the others fall out of focus.
          const blur = Math.min(Math.abs(where - i), 2) * 5 * lift;
          const drawn = tween(frame, LOOK[i] - 6, LOOK[i] + 8, 0, 1, EASE);
          const stated = spring({
            frame: frame - LOOK[i] - 4,
            fps,
            config: { damping: 11, mass: 0.5, stiffness: 190 },
          });
          const gone = tween(where - i, 1.25, 1.7, 0, 1);
          const face = (copy: string): React.ReactNode => (
            <div style={{ width: PANE.width / PANE.zoom, zoom: PANE.zoom }}>
              <MarketCard
                market={m}
                wide
                drawn={drawn}
                stated={stated}
                copy={copy}
                style={{
                  // Thicker glass than on a phone: more of the light behind it shows,
                  // and the edge towards the light is bright.
                  boxShadow: `inset 0 1px 0 rgba(255,255,255,0.28), inset 1px 0 0 rgba(255,255,255,0.1), 0 24px 60px -30px rgba(0,0,0,0.9), 0 0 60px -20px ${fade(tone, 0.5)}`,
                  backdropFilter: "blur(14px)",
                }}
              />
            </div>
          );
          return (
            <div
              key={m.slug}
              style={{
                position: "absolute",
                left: x,
                top: y,
                width: PANE.width,
                translate: "-50% -24.6%",
                transformOrigin: "50% 24.6%",
                transform: `scale(${size}) rotateY(${turn}deg)`,
                opacity: (1 - gone) * tween(frame, i * 2, 4 + i * 2, 0, 1),
                filter: blur > 0.3 ? `blur(${blur}px)` : undefined,
                zIndex: 10 - Math.round(Math.abs(where - i) * 3),
              }}
            >
              <div style={{ position: "relative" }}>
                {face("")}
                <div
                  style={{ position: "absolute", inset: 0, zoom: PANE.zoom }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: PANE.width / PANE.zoom,
                    }}
                  >
                    <TopEdge />
                  </div>
                </div>
              </div>
              {/* The pane's faint reflection in the ground it stands over. */}
              <div
                style={{
                  marginTop: 14,
                  scale: "1 -1",
                  opacity: 0.16 * lift,
                  maskImage: "linear-gradient(to top, #000, transparent 55%)",
                  WebkitMaskImage:
                    "linear-gradient(to top, #000, transparent 55%)",
                }}
              >
                {face("-mirror")}
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
