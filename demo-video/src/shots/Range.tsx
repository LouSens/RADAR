import { useThree } from "@react-three/fiber";
import { useMemo } from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import {
  BoxGeometry,
  Color,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  Plane,
  Vector3,
} from "three";
import market from "../fixtures/market.json";
import { C } from "../theme";
import { Card, Floor, Numerals, figureWidth, glass } from "../three/Kit";
import { Stage, project, type View } from "../three/Stage";
import { useLoaded, type Assets } from "../three/assets";
import { EASE_IN_OUT, tween } from "../timing";
import { ASKED, Ring } from "../World";

const { range } = market;

// The scene, in its own units. The prices run along X; the bars stand on the floor and
// the two figures stand in front of them.
const SPAN = 9;
const TALL = 2.3;
const FRONT = 1.5;
const first = range.edges[0];
const last = range.edges[range.edges.length - 1];
const x = (value: number): number =>
  -SPAN / 2 + ((value - first) / (last - first)) * SPAN;

const X_LOW = x(range.low);
const X_HIGH = x(range.high);
const X_NOW = x(range.startPrice);
const MOST = Math.max(...range.counts);
const BAR = SPAN / range.counts.length;
const NOW_BAR = Math.floor((X_NOW + SPAN / 2) / BAR);

/** How tall the one price stands, and how tall each end of the range comes to rest. */
const WHOLE = 1.15;
const RESTING = 0.46;
const WIDE = figureWidth(range.startPrice, "dollar");

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** When the cut starts to open and when the two figures land. */
export const OPEN = [ASKED + 6, ASKED + 38] as const;
/** When the first bar starts to rise, and how much later each one farther out starts. */
export const RISE = ASKED + 18;
const STAGGER = 1.3;
/** When the bars fold away into the card, and when the card stands. */
export const FOLD = [ASKED + 56, ASKED + 72] as const;
/** When the ring spreads from the range on the card. */
export const PINGED = FOLD[1] + 2;

/** The clear space between the two figures, `open` of the way through the move. */
const gapAt = (open: number): number =>
  (X_HIGH - X_LOW) * open - WIDE * mix(WHOLE, RESTING, open);
/** How far through the move the space first exceeds one digit: counting starts there. */
const COUNT_FROM = (() => {
  for (let open = 0; open <= 1; open += 0.001) {
    if (gapAt(open) > 0.7 * mix(WHOLE, RESTING, open)) {
      return open;
    }
  }
  return 1;
})();

/** The card of the app the picture resolves into: how wide, and where it stands. */
const CARD = { width: 7.6, z: -0.2, lean: -0.1 } as const;
const CARD_TALL = (CARD.width * 480) / 1118;
/** Where "$78,964 to $88,767" is on the card's face, from its top left, as shares. */
const ANSWER = { u: 0.118, v: 0.56 } as const;

/** Low, and pushing in the whole time; it rises a little to meet the card. */
const camera = (frame: number): View => {
  const push = tween(frame, 0, 105, 0, 1, (t) => t);
  const up = tween(frame, FOLD[0] - 6, FOLD[1] + 6, 0, 1, EASE_IN_OUT);
  return {
    position: [0.9 - push * 0.7, 0.75 + up * 0.75, 11.2 - push * 2.2 - up * 0.3],
    target: [0, 1.55 + up * 0.15, 0],
    focus: [0, 0.6, mix(FRONT, CARD.z, up)],
    aperture: 0.05,
    fov: 30,
  };
};

/** Lets one material be cut by a plane of its own. Three leaves this off by default. */
const Cuts: React.FC = () => {
  const { gl } = useThree();
  gl.localClippingEnabled = true;
  return null;
};

const Scene: React.FC<{
  readonly assets: Assets;
  readonly frame: number;
  readonly fps: number;
}> = ({ assets, frame, fps }) => {
  const bar = useMemo(() => new BoxGeometry(BAR * 0.78, 1, 0.55), []);
  const inside = useMemo(() => glass(C.btc, { glow: 0.32, rough: 0.2 }), []);
  const outside = useMemo(() => glass("#4d4741", { glow: 0.05, rough: 0.3 }), []);
  const lit = useMemo(
    () => new MeshBasicMaterial({ color: "#ffc59b", toneMapped: false }),
    [],
  );
  const dull = useMemo(
    () => new MeshBasicMaterial({ color: "#6b625a", toneMapped: false }),
    [],
  );
  const cap = useMemo(() => new BoxGeometry(BAR * 0.78, 0.02, 0.55), []);
  // The two copies of the price: each is shown on its own side of the cut.
  const [left, right] = useMemo(() => {
    const make = (side: 1 | -1): MeshPhysicalMaterial =>
      new MeshPhysicalMaterial({
        color: "#d9dce6",
        roughness: 0.25,
        clearcoat: 1,
        clearcoatRoughness: 0.1,
        envMapIntensity: 1,
        emissive: new Color("#d9dce6"),
        emissiveIntensity: 0.05,
        clippingPlanes: [new Plane(new Vector3(side, 0, 0), 0)],
      });
    return [make(-1), make(1)];
  }, []);

  // One move, on one curve. The price is two copies of itself standing exactly
  // together, the left one seen only left of a cut and the right one only right of it.
  // Both show the same value while they part, so no frame has a figure made of two
  // different numbers. Once they stand clear, with more than a digit between them, each
  // counts to its end of the range as it finishes its journey.
  const open = tween(frame, OPEN[0], OPEN[1], 0, 1, EASE_IN_OUT);
  const size = mix(WHOLE, RESTING, open);
  const lowX = mix(X_NOW, X_LOW, open);
  const highX = mix(X_NOW, X_HIGH, open);
  const seam = (lowX + highX) / 2;
  const gap = Math.max(gapAt(open), 0);
  // A plane keeps what is on the side its normal points to: normal · p + constant > 0.
  left.clippingPlanes?.[0].set(new Vector3(-1, 0, 0), seam - gap / 2 + Math.min(gap, 0.03));
  right.clippingPlanes?.[0].set(new Vector3(1, 0, 0), -(seam + gap / 2 - Math.min(gap, 0.03)));
  const counted = tween(open, COUNT_FROM, 1, 0, 1, (t) => t);

  const fold = tween(frame, FOLD[0], FOLD[1], 0, 1, EASE_IN_OUT);
  const stand = spring({
    frame: frame - FOLD[0] - 3,
    fps,
    config: { damping: 14, mass: 0.7, stiffness: 120 },
  });
  const away = 1 - fold;

  return (
    <Floor tint={C.btc}>
      <Cuts />
      {range.counts.map((count, i) => {
        const centre = -SPAN / 2 + (i + 0.5) * BAR;
        const within =
          range.edges[i + 1] > range.low && range.edges[i] < range.high;
        const grown =
          spring({
            frame: frame - RISE - Math.abs(i - NOW_BAR) * STAGGER,
            fps,
            config: { damping: 13, mass: 0.6, stiffness: 150 },
          }) * away;
        const tall = (count / MOST) * TALL * grown;
        if (tall < 0.01) {
          return null;
        }
        return (
          <group key={range.edges[i]} position={[centre, 0, 0]}>
            <mesh
              geometry={bar}
              material={within ? inside : outside}
              position={[0, tall / 2, 0]}
              scale={[1, tall, 1]}
            />
            {grown > 0.02 && (
              <mesh
                geometry={cap}
                material={within ? lit : dull}
                position={[0, tall + 0.01, 0]}
              />
            )}
          </group>
        );
      })}
      {away > 0.02 && (
        <>
          <Numerals
            kit={assets.kit}
            value={mix(range.startPrice, range.low, counted)}
            position={[lowX, 0, FRONT]}
            scale={size * away}
            material={left}
          />
          <Numerals
            kit={assets.kit}
            value={mix(range.startPrice, range.high, counted)}
            position={[highX, 0, FRONT]}
            scale={size * away}
            material={right}
          />
        </>
      )}
      {/* The proof: the app's own card stands up from the floor where the bars were. */}
      {stand > 0.001 && (
        <group
          position={[0, 0.04, CARD.z]}
          rotation={[mix(-Math.PI / 2, CARD.lean, stand), 0, 0]}
        >
          <Card
            face={assets.cards.range}
            width={CARD.width}
            position={[0, CARD_TALL / 2, 0]}
            lit={tween(stand, 0.2, 0.9, 0.25, 1, (t) => t)}
          />
        </group>
      )}
    </Floor>
  );
};

/**
 * Shot 5. The price as solid figures is cut down the middle into the low and the high
 * of the week's range, the simulated outcomes rise between them, and the whole picture
 * folds into the app's own card. Figures: fixtures/market.json.
 */
export const Range: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  // While the question stands in the middle of the frame the picture waits behind it.
  const shown = tween(frame, ASKED - 4, ASKED + 10, 0.3, 1, (t) => t);
  const view = camera(frame);
  const answer = project(view, [
    (ANSWER.u - 0.5) * CARD.width,
    0.04 + (1 - ANSWER.v) * CARD_TALL * Math.cos(CARD.lean),
    CARD.z + (1 - ANSWER.v) * CARD_TALL * Math.sin(CARD.lean) + 0.2,
  ]);

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={C.btc}
        camera={camera}
        turn={0.9}
        style={{ opacity: shown }}
      >
        <Scene assets={assets} frame={frame} fps={fps} />
      </Stage>
      <Ring since={frame - PINGED} x={answer.x} y={answer.y} reach={190} />
    </AbsoluteFill>
  );
};
