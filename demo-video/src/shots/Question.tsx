import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Quaternion, Vector3 } from "three";
import fall from "../fixtures/fall.json";
import { C } from "../theme";
import { Floor, KIT, Piece, each } from "../three/Kit";
import { Stage, type MoveAt, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { BEAT, EASE, tween } from "../timing";
import { MARGIN, Small, hero } from "../Type";
import { formatPrice } from "../ui/kit";

const closes = fall.hourlyCloses;

/** The price changes this often, in frames. */
export const TICK = 3;
/** The hours the shot plays through: the day of the fall, ending on its last hour. */
export const HOURS = 30;
const shown = closes.slice(closes.length - HOURS);

/** How large the coin is in the scene, against the size it is made at. */
const SIZE = 1.7;
const RADIUS = KIT.coin.radius * SIZE;
const HALF = (KIT.coin.depth * SIZE) / 2;

/** When the coin stops spinning upright and starts to go over, and when it lands. */
export const TOPPLE = 26;
export const LANDS = 41;
/** The three words, a beat apart: each one tips the coin the other way. */
export const WORDS = [BEAT * 3, BEAT * 4, BEAT * 5] as const;

const FACE = new Vector3(0, 0, 1);

/**
 * The coin at a moment of the shot: where its middle is and how it is turned. It spins
 * on its edge and slows, leans, goes over, lands with a small bounce, and then rolls
 * round its rim as a dropped coin does, more quickly as it settles. Each word knocks it
 * again from the other side.
 */
const coinAt = (
  frame: number,
): { position: Vector3; turn: Quaternion } => {
  // Upright, turning about the vertical: fast at first, nearly stopped as it goes over.
  const spin = 6.5 * (1 - Math.exp(-frame / 13)) + frame * 0.02;
  let normal: Vector3;
  let lift = 0;
  if (frame < LANDS) {
    // The lean grows slowly, then gravity takes it: a quarter turn from upright to flat.
    const lean = tween(frame, 6, TOPPLE, 0, 0.09, (t) => t * t);
    const over = tween(frame, TOPPLE, LANDS, 0, 1, (t) => t * t * t);
    const angle = (Math.PI / 2) * (1 - Math.min(lean + over, 1));
    normal = new Vector3(
      Math.sin(angle) * Math.cos(spin),
      Math.cos(angle),
      Math.sin(angle) * Math.sin(spin),
    );
  } else {
    // Flat, rolling round its rim. Every knock adds a tilt that dies away, and starts
    // from the side opposite the one before.
    const knocks = [LANDS, ...WORDS];
    let x = 0;
    let z = 0;
    knocks.forEach((at, i) => {
      const since = frame - at;
      if (since < 0) {
        return;
      }
      const size = (i === 0 ? 0.34 : 0.26) * Math.exp(-since / (i === 0 ? 7 : 9));
      // It rolls faster as it settles.
      const round = 0.5 * since + 0.012 * since * since + i * Math.PI + 0.6;
      x += size * Math.cos(round);
      z += size * Math.sin(round);
    });
    normal = new Vector3(x, 1, z).normalize();
    const since = frame - LANDS;
    lift = 0.2 * Math.exp(-since / 4) * Math.abs(Math.sin((Math.PI * since) / 6));
  }
  // Its rim rests on the floor: the middle is as high as the tilt puts it.
  const flat = Math.abs(normal.y);
  const height = RADIUS * Math.sqrt(1 - flat * flat) + HALF * flat + lift;
  const turn = new Quaternion().setFromUnitVectors(FACE, normal);
  // The struck face turns about its own middle as well, so the sign is seen to move.
  turn.multiply(new Quaternion().setFromAxisAngle(FACE, spin * 0.35));
  return { position: new Vector3(0, height, 0), turn };
};

const move: MoveAt = (frame, scene) => {
  const { position, turn } = coinAt(frame);
  each(scene, "coin", (coin) => {
    coin.position.copy(position);
    coin.quaternion.copy(turn);
  });
};

/** A slow push towards the coin, a little round it, focused on it. */
const camera = (frame: number): View => {
  const push = tween(frame, 0, 105, 0, 1, (t) => t);
  const round = -0.34 + push * 0.2;
  const far = 7.4 - push * 1.1;
  return {
    position: [
      -1.75 + Math.sin(round) * far,
      2.5 - push * 0.5,
      Math.cos(round) * far,
    ],
    target: [-1.75, 0.95, 0],
    focus: [0, 0.3, 0],
    aperture: 0.045,
    fov: 30,
  };
};

/**
 * Shot 1. Bitcoin as a coin: it spins on its edge, goes over and falls, and wobbles on
 * the floor while the three things a holder might do are asked. Beside it the price
 * falls through the real hours of the day (fixtures/fall.json). The words are in
 * Questions.
 */
export const Question: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const step = Math.min(Math.floor(frame / TICK), HOURS - 1);
  const since = frame - step * TICK;
  const price = shown[step];
  const before = shown[Math.max(step - 1, 0)];
  const up = price >= before;
  // Each new price knocks the figure a little the way it moved, and it settles back.
  const knock =
    step === 0 || step === HOURS - 1
      ? 0
      : 1 - tween(since, 0, TICK, 0, 1, EASE);
  const fast = frame >= TOPPLE - 2 && frame < LANDS + 8;

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={C.btc}
        camera={camera}
        move={move}
        shutter={fast ? 0.6 : 0.35}
        turn={0.6}
      >
        <Floor tint={C.btc}>
          <Piece kit={assets.kit} piece="coin" name="coin" scale={SIZE} />
        </Floor>
      </Stage>

      <Small
        at={-20}
        text={
          <span style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: C.btc,
              }}
            />
            Bitcoin
            <span style={{ color: up ? C.calm : C.alert }}>
              {step === 0
                ? ""
                : `${up ? "▲" : "▼"} ${Math.abs((price / before - 1) * 100).toFixed(2)}% this hour`}
            </span>
          </span>
        }
        style={{ position: "absolute", left: MARGIN, top: 700 }}
      />
      <div
        style={{
          ...hero,
          position: "absolute",
          left: MARGIN - 8,
          top: 772,
          fontSize: 200,
          translate: `0 ${(up ? -1 : 1) * knock * 10}px`,
        }}
      >
        {formatPrice(price)}
      </div>
    </AbsoluteFill>
  );
};
