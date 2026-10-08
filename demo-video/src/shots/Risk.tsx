import { useMemo } from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Color, MeshPhysicalMaterial } from "three";
import portfolio from "../fixtures/portfolio.json";
import { C, FEATURES, FONT } from "../theme";
import { Card, Floor, KIT, Numerals, Piece, glass, type PieceName } from "../three/Kit";
import { Stage, project, type View } from "../three/Stage";
import { useLoaded, type Assets } from "../three/assets";
import { COPY, EASE_IN_OUT, tween } from "../timing";
import { MARGIN, Rise, Small } from "../Type";
import { ASKED, Ring } from "../World";

/**
 * What each holding is in the scene. A share of 1 would stand `full` units tall; the
 * things are sized by the square root of their share, so that a thing with four times
 * the share looks four times as large on the screen, not sixty-four.
 */
const THINGS: Readonly<
  Record<string, { piece: PieceName; unit: number; lift?: number; turn?: number }>
> = {
  "BTC/USD": { piece: "coin", unit: 1.5, lift: KIT.coin.radius },
  "PAXG/USD": { piece: "ingot", unit: 1.55 },
  SPY: { piece: "stocks", unit: 1.45 },
  USD: { piece: "chip", unit: 1.6 },
};
const sized = (share: number): number => Math.sqrt(share) * 1.55;

const holdings = portfolio.holdings;
const bitcoin = holdings[0];

/** The glass ring the holdings stand on. */
const RING = 2.5;

/** When the holdings arrive, when they change to their share of the risk, and when the
 *  number has finished counting. */
export const ARRIVE = 2;
export const MONEY = [ARRIVE, ARRIVE + 12] as const;
export const RISK = [ASKED + 24, ASKED + 44] as const;
/** When the picture folds into the card, and when the card stands. */
export const FOLD = [ASKED + 58, ASKED + 74] as const;

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** A slow turn round the ring the whole time, from a little above. */
const camera = (frame: number): View => {
  const round = -0.25 + frame * 0.0035;
  const up = tween(frame, FOLD[0] - 4, FOLD[1] + 6, 0, 1, EASE_IN_OUT);
  const far = 13.4 - frame * 0.014;
  return {
    position: [Math.sin(round) * far, 4.4 - up * 2.1, Math.cos(round) * far],
    target: [0, 1.75 - up * 0.35, 0],
    focus: [0, 1, 0],
    aperture: 0.045,
    fov: 30,
  };
};

/** Where the middle of the number stands. */
const NUMBER = { y: 3.05, tall: 1.2 } as const;
const CARD = { width: 6.6 } as const;
const CARD_TALL = (CARD.width * 310) / 738;
const Scene: React.FC<{
  readonly assets: Assets;
  readonly frame: number;
  readonly fps: number;
}> = ({ assets, frame, fps }) => {
  const ring = useMemo(() => glass("#9fb7c4", { glow: 0.04, rough: 0.12 }), []);
  const figure = useMemo(
    () =>
      new MeshPhysicalMaterial({
        color: "#eef0f6",
        roughness: 0.22,
        clearcoat: 1,
        clearcoatRoughness: 0.1,
        emissive: new Color("#eef0f6"),
        emissiveIntensity: 0.12,
      }),
    [],
  );
  const counted = tween(frame, RISK[0], RISK[1], 0, 1, EASE_IN_OUT);
  // The number takes Bitcoin's colour as it becomes Bitcoin's share of the risk.
  figure.color.set("#eef0f6").lerp(new Color("#f0a878"), counted);
  figure.emissive.copy(figure.color);
  figure.emissiveIntensity = 0.12 + counted * 0.25;

  const fold = tween(frame, FOLD[0], FOLD[1], 0, 1, EASE_IN_OUT);
  const away = 1 - fold;
  const stand = spring({
    frame: frame - FOLD[0] - 3,
    fps,
    config: { damping: 14, mass: 0.7, stiffness: 120 },
  });
  // The ring and what stands on it turn slowly, against the camera.
  const turned = -frame * 0.006;

  return (
    <Floor tint={C.accent}>
      <group rotation={[0, turned, 0]} scale={away}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]} material={ring}>
          <torusGeometry args={[RING, 0.07, 20, 160]} />
        </mesh>
        {holdings.map((holding, i) => {
          const thing = THINGS[holding.symbol];
          const angle = (i / holdings.length) * Math.PI * 2 + 0.95;
          // Each arrives at its share of the money, a few frames after the one before,
          // then springs to its share of the risk and settles.
          const arrived = spring({
            frame: frame - MONEY[0] - i * 3,
            fps,
            config: { damping: 13, mass: 0.6, stiffness: 140 },
          });
          const changed = spring({
            frame: frame - RISK[0] - i * 3,
            fps,
            config: { damping: 12, mass: 0.8, stiffness: 110 },
          });
          const size =
            Math.max(mix(sized(holding.money) * arrived, sized(holding.risk), changed), 0) *
            thing.unit;
          return (
            <group
              key={holding.symbol}
              position={[Math.sin(angle) * RING, 0.05, Math.cos(angle) * RING]}
              rotation={[0, angle + Math.PI / 2 + frame * 0.012, 0]}
              scale={Math.max(size, 0.0001)}
            >
              {holding.symbol === "USD" ? (
                // Cash is a short stack of chips.
                [0, 1, 2, 3].map((n) => (
                  <Piece
                    key={n}
                    kit={assets.kit}
                    piece="chip"
                    position={[n % 2 ? 0.02 : -0.02, n * KIT.chip.depth * 1.04, 0]}
                    rotation={[0, n * 0.7, 0]}
                  />
                ))
              ) : (
                <Piece
                  kit={assets.kit}
                  piece={thing.piece}
                  position={[0, thing.lift ?? 0, 0]}
                />
              )}
            </group>
          );
        })}
      </group>
      {away > 0.02 && (
        <Numerals
          kit={assets.kit}
          value={mix(bitcoin.money, bitcoin.risk, counted) * 100}
          unit="percent"
          position={[0, NUMBER.y - NUMBER.tall / 2, 0]}
          rotation={[0, -0.25 + frame * 0.0035, 0]}
          scale={NUMBER.tall * away}
          material={figure}
        />
      )}
      {stand > 0.001 && (
        <group
          position={[0, 0.04, 0]}
          rotation={[mix(-Math.PI / 2, -0.12, stand), -0.25 + frame * 0.0035, 0, "YXZ"]}
        >
          <Card
            face={assets.cards.risk}
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
 * Shot 6. The four holdings as things on a turning glass ring, each as large as its
 * share of the money; then each as large as its share of the risk, and the number in
 * the middle goes from Bitcoin's share of the one to its share of the other. The
 * picture folds into the app's own card. Figures: the made-up example in
 * fixtures/portfolio.json.
 */
export const Risk: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const shown = tween(frame, ASKED - 4, ASKED + 10, 0.3, 1, (t) => t);
  const view = camera(frame);
  const fold = tween(frame, FOLD[0], FOLD[1], 0, 1, EASE_IN_OUT);
  const under = project(view, [0, NUMBER.y - NUMBER.tall / 2 - 0.12, 0]);
  const middle = project(view, [0, NUMBER.y, 0]);
  const label: React.CSSProperties = {
    position: "absolute",
    left: under.x,
    top: under.y,
    translate: "-50% 0",
    fontFamily: FONT,
    fontFeatureSettings: FEATURES,
    fontSize: 48,
    fontWeight: 500,
    letterSpacing: "-0.011em",
    whiteSpace: "nowrap",
  };

  return (
    <AbsoluteFill>
      <Stage
        room={assets.room}
        light={C.accent}
        camera={camera}
        turn={0.4}
        style={{ opacity: shown }}
      >
        <Scene assets={assets} frame={frame} fps={fps} />
      </Stage>
      {/* Whose share the number is: of the money, then of the risk. */}
      <div style={label}>
        <Rise at={2} out={RISK[0] + 2} style={{ color: C.muted }}>
          of your money
        </Rise>
      </div>
      <div style={{ ...label, opacity: fold > 0.5 ? 0 : 1 }}>
        <Rise at={RISK[1] - 8} out={FOLD[0]} style={{ color: C.btc }}>
          of your risk
        </Rise>
      </div>
      <Ring since={frame - RISK[1]} x={middle.x} y={middle.y} reach={230} />
      <Small
        text={COPY.example}
        at={ASKED}
        style={{ position: "absolute", left: MARGIN, top: 980 }}
      />
    </AbsoluteFill>
  );
};
