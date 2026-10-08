import { AbsoluteFill, spring, useCurrentFrame } from "remotion";
import { Matrix4, Quaternion, Vector3 } from "three";
import fall from "../fixtures/fall.json";
import { C } from "../theme";
import { Coin, Floor, KIT, each } from "../three/Kit";
import { Stage, type MoveAt, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { BEAT, EASE, EASE_IN_OUT, FPS, HEIGHT, shot, tween } from "../timing";
import { MARGIN, Small, hero } from "../Type";
import { formatPrice } from "../ui/kit";

const closes = fall.hourlyCloses;

/** The price changes this often, in frames. */
export const TICK = 3;
/** The hours the shot plays through: the day of the fall, ending on its last hour. */
export const HOURS = 28;
const shown = closes.slice(closes.length - HOURS);

/** How large the coin is in the scene, against the size it is made at. */
const SIZE = 1.7;
const RADIUS = KIT.coin.radius * SIZE;
const HALF = (KIT.coin.depth * SIZE) / 2;

/** When the coin stops spinning upright and starts to go over, and when it lands. */
export const TOPPLE = 26;
export const LANDS = 41;
/** When the coin is flicked up on to its rim, to spin round and face us. */
export const EXIT = 92;
/** The three words, a beat apart: each one tips the coin the other way. */
export const WORDS = [BEAT * 3, BEAT * 3 + 13, BEAT * 3 + 26] as const;
/** When the shot's words and its price leave, for the coin to stand alone. */
export const CLEARS = EXIT - 6;
/** When the coin gives way to the mark (shots/Meet): its length, past the shot's end. */
export const GIVES = 12;

const END = shot("question").duration;
const FACE = new Vector3(0, 0, 1);
const UP = new Vector3(0, 1, 0);
const FOV = 30;
/** Where the camera ends, square on to the coin, and how the coin faces it. */
const LAST = { x: 0, y: RADIUS + 0.35, z: 5.2 } as const;
const FACING = new Vector3(LAST.x, LAST.y - RADIUS, LAST.z).normalize();
/** How far round it spins as it comes up, before it stops facing us. */
const TURNS = 3 * Math.PI;

/**
 * The coin's rim in the frame once it stands facing the camera: its middle and its
 * radius, in pixels. The mark's ring starts exactly there (shots/Meet).
 */
export const RESTS = {
  x: 960,
  y: 540,
  r:
    (RADIUS * (HEIGHT / 2)) /
    Math.tan((FOV * Math.PI) / 360) /
    Math.hypot(LAST.y - RADIUS, LAST.z),
} as const;

/**
 * The coin at a moment of the shot: where its middle is and how it is turned. It spins
 * on its edge and slows, leans, goes over, lands with a small bounce, and then rolls
 * round its rim as a dropped coin does, more quickly as it settles. Each word knocks it
 * again from the other side. At the end it is flicked back up on to its rim, spins
 * round, and stops facing the camera, a little past it and back.
 */
const coinAt = (frame: number): { position: Vector3; turn: Quaternion } => {
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
      const size =
        (i === 0 ? 0.34 : 0.26) * Math.exp(-since / (i === 0 ? 7 : 9));
      // It rolls faster as it settles.
      const round = 0.5 * since + 0.012 * since * since + i * Math.PI + 0.6;
      x += size * Math.cos(round);
      z += size * Math.sin(round);
    });
    normal = new Vector3(x, 1, z).normalize();
    const since = frame - LANDS;
    lift =
      0.2 * Math.exp(-since / 4) * Math.abs(Math.sin((Math.PI * since) / 6));
  }
  const turn = new Quaternion().setFromUnitVectors(FACE, normal);
  // The struck face turns about its own middle as well, so the sign is seen to move.
  turn.multiply(new Quaternion().setFromAxisAngle(FACE, spin * 0.35));

  const leaving = frame - EXIT;
  if (leaving > 0) {
    const up = tween(leaving, 0, 9, 0, 1, EASE);
    // A spring: it comes round fast, goes a little past facing us, and comes back.
    const round = spring({
      frame: leaving,
      fps: FPS,
      config: { damping: 15, mass: 0.9, stiffness: 120 },
    });
    const facing = FACING.clone().applyAxisAngle(UP, (round - 1) * TURNS);
    const side = new Vector3().crossVectors(UP, facing).normalize();
    const top = new Vector3().crossVectors(facing, side);
    const upright = new Quaternion().setFromRotationMatrix(
      new Matrix4().makeBasis(side, top, facing),
    );
    turn.slerp(upright, up);
    normal = FACE.clone().applyQuaternion(turn);
    lift *= 1 - up;
  }
  // Its rim rests on the floor: the middle is as high as the tilt puts it.
  const flat = Math.min(Math.abs(normal.y), 1);
  const height = RADIUS * Math.sqrt(1 - flat * flat) + HALF * flat + lift;
  return { position: new Vector3(0, height, 0), turn };
};

const move: MoveAt = (frame, scene) => {
  const { position, turn } = coinAt(frame);
  each(scene, "coin", (coin) => {
    coin.position.copy(position);
    coin.quaternion.copy(turn);
  });
};

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/**
 * A slow push towards the coin, a little round it; then, as the coin comes up, one
 * move in to stand square in front of it, the coin in the middle of the frame.
 */
const camera = (frame: number): View => {
  const push = tween(frame, 0, 105, 0, 1, (t) => t);
  const round = -0.34 + push * 0.2;
  const far = 7.4 - push * 1.1;
  const in_ = tween(frame, EXIT + 3, END + 2, 0, 1, EASE_IN_OUT);
  return {
    position: [
      mix(-1.75 + Math.sin(round) * far, LAST.x, in_),
      mix(2.5 - push * 0.5, LAST.y, in_),
      mix(Math.cos(round) * far, LAST.z, in_),
    ],
    target: [mix(-1.75, 0, in_), mix(0.95, RADIUS, in_), 0],
    focus: [0, mix(0.3, RADIUS, in_), 0],
    aperture: mix(0.045, 0.012, in_),
    fov: FOV,
  };
};

/**
 * Shot 1. Bitcoin as a coin: it spins on its edge, goes over and falls, and wobbles on
 * the floor while the three things a holder might do are asked. Beside it the price
 * falls through the real hours of the day (fixtures/fall.json). Then the words leave,
 * the coin comes up on to its rim and stops facing the camera, the camera goes in, and
 * its copper turns to the mark's colour as the sign on its face goes: its rim is the
 * mark's ring (shots/Meet). The words are in Questions.
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
  const fast = (frame >= TOPPLE - 2 && frame < LANDS + 8) || frame >= EXIT;
  const cleared = tween(frame, CLEARS, CLEARS + 8, 0, 1, EASE_IN_OUT);

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={C.btc}
        camera={camera}
        move={move}
        shutter={fast ? 0.6 : 0.35}
        turn={0.6}
        style={{
          opacity: 1 - tween(frame, END + 2, END + GIVES, 0, 1, (t) => t),
        }}
      >
        <Floor tint={C.btc}>
          <Coin
            kit={assets.kit}
            name="coin"
            scale={SIZE}
            tint={tween(frame, END, END + GIVES - 2, 0, 1, (t) => t)}
            relief={1 - tween(frame, END - 2, END + 6, 0, 1, (t) => t)}
          />
        </Floor>
      </Stage>

      <Small
        at={-20}
        out={CLEARS}
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
      {/* The price leaves as type does: up, out through the top of its own line. */}
      <div
        style={{
          position: "absolute",
          left: MARGIN - 8,
          top: 752,
          padding: "20px 0 30px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            ...hero,
            fontSize: 200,
            translate: `0 ${(up ? -1 : 1) * knock * 10 - cleared * 280}px`,
          }}
        >
          {formatPrice(price)}
        </div>
      </div>
    </AbsoluteFill>
  );
};
