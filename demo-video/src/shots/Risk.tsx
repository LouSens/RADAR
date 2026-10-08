import { AbsoluteFill, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, FONT, NUM_FEATURES, fade } from "../theme";
import { EASE, EASE_IN_OUT, tween } from "../timing";
import { ExampleNote, TONE, label } from "../ui/kit";
import { Words } from "../Words";

const holdings = portfolio.holdings;
const bitcoin = holdings[0];

// The two rings (viz.tsx, Donut: radii 38 and 52 and a stroke of 9 on a box of 120),
// five times the size.
const CX = 560;
const CY = 548;
const INNER = 190;
const OUTER = 260;
const STROKE = 45;

/** One ring, drawn clockwise from twelve o'clock as far as `drawn` of the way round. */
const Ring: React.FC<{
  readonly radius: number;
  readonly share: (holding: (typeof holdings)[number]) => number;
  readonly drawn: number;
}> = ({ radius, share, drawn }) => {
  const round = 2 * Math.PI * radius;
  let used = 0;
  return (
    <>
      <circle
        cx={CX}
        cy={CY}
        r={radius}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={STROKE}
      />
      {holdings.map((holding) => {
        const length = share(holding) * round;
        const start = used;
        used += length;
        const seen = Math.min(Math.max(drawn * round - start, 0), length - 6);
        if (seen <= 0) {
          return null;
        }
        const hero = holding.symbol === bitcoin.symbol;
        return (
          <circle
            key={holding.symbol}
            cx={CX}
            cy={CY}
            r={radius}
            fill="none"
            stroke={TONE[holding.tone]}
            strokeOpacity={hero ? 1 : 0.62}
            strokeWidth={STROKE}
            strokeDasharray={`${seen} ${round}`}
            strokeDashoffset={-start}
            style={
              hero
                ? { filter: `drop-shadow(0 0 16px ${fade(C.btc, 0.55)})` }
                : undefined
            }
          />
        );
      })}
    </>
  );
};

/** A counted share with its words: "12% of your money." */
const Counted: React.FC<{
  readonly value: number;
  readonly words: string;
  readonly at: number;
  readonly colour: string;
  readonly top: number;
}> = ({ value, words, at, colour, top }) => {
  const frame = useCurrentFrame();
  const arrive = tween(frame, at, at + 10, 0, 1, EASE);
  const count = Math.round(tween(frame, at, at + 20, 0, value * 100, EASE));
  return (
    <div
      style={{
        position: "absolute",
        left: 930,
        top,
        display: "flex",
        alignItems: "baseline",
        gap: 28,
      }}
    >
      <span
        style={{
          width: 400,
          textAlign: "right",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontVariantNumeric: "tabular-nums",
          fontSize: 176,
          fontWeight: 700,
          letterSpacing: "-0.045em",
          lineHeight: 1,
          color: colour,
          opacity: arrive,
          filter: arrive < 1 ? `blur(${(1 - arrive) * 16}px)` : undefined,
        }}
      >
        {count}%
      </span>
      <Words text={words} at={at + 4} size={62} weight={600} />
    </div>
  );
};

/**
 * Shot 6. Where the money is and where the risk is: the inner ring is how the account is
 * split, the outer ring how its swings are. Bitcoin is a sliver of one and most of the
 * other. Figures: the made-up example in fixtures/portfolio.json.
 */
export const Risk: React.FC = () => {
  const frame = useCurrentFrame();
  const money = tween(frame, 16, 38, 0, 1, EASE_IN_OUT);
  const risk = tween(frame, 46, 68, 0, 1, EASE_IN_OUT);
  const names = tween(frame, 20, 32, 0, 1);

  return (
    <AbsoluteFill>
      <svg
        width={1920}
        height={1080}
        style={{
          position: "absolute",
          inset: 0,
          rotate: "-90deg",
          transformOrigin: `${CX}px ${CY}px`,
        }}
      >
        <Ring radius={INNER} share={(h) => h.money} drawn={money} />
        <Ring radius={OUTER} share={(h) => h.risk} drawn={risk} />
      </svg>

      <div
        style={{
          position: "absolute",
          left: CX,
          top: CY,
          translate: "-50% -50%",
          textAlign: "center",
          fontFamily: FONT,
          opacity: names,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 14,
            fontSize: 40,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            color: C.ink,
          }}
        >
          <span
            style={{
              width: 18,
              height: 18,
              borderRadius: "50%",
              background: C.btc,
            }}
          />
          Bitcoin
        </div>
        <div style={{ ...label, fontSize: 20, marginTop: 6 }}>
          {risk > 0 ? "Money · Risk" : "Money"}
        </div>
      </div>

      {/* viz.tsx, Legend, and the caption the rings carry in the app. */}
      <div
        style={{
          position: "absolute",
          left: CX,
          top: CY + OUTER + 58,
          translate: "-50% 0",
          display: "flex",
          gap: 36,
          fontFamily: FONT,
          fontSize: 24,
          color: C.muted,
          whiteSpace: "nowrap",
          opacity: names,
        }}
      >
        {holdings.map((holding) => (
          <span
            key={holding.symbol}
            style={{ display: "flex", alignItems: "center", gap: 10 }}
          >
            <span
              style={{
                width: 13,
                height: 13,
                borderRadius: "50%",
                background: TONE[holding.tone],
              }}
            />
            {holding.name}
          </span>
        ))}
      </div>

      <Counted
        value={bitcoin.money}
        words="of your money."
        at={18}
        colour={C.ink}
        top={318}
      />
      <Counted
        value={bitcoin.risk}
        words="of your risk."
        at={48}
        colour={C.btc}
        top={548}
      />
      <div
        style={{
          position: "absolute",
          left: 930 + 400 + 28,
          top: 770,
          fontFamily: FONT,
          fontSize: 26,
          color: C.faint,
          opacity: tween(frame, 60, 72, 0, 1),
        }}
      >
        Inner ring: money. Outer ring: risk.
      </div>
      <ExampleNote opacity={names} />
    </AbsoluteFill>
  );
};
