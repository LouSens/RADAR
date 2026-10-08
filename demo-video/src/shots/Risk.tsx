import { AbsoluteFill, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, FONT, fade } from "../theme";
import { COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import { HERO, Headline, MARGIN, Rise, hero } from "../Type";
import { ExampleNote, TONE, label } from "../ui/kit";

const holdings = portfolio.holdings;
const bitcoin = holdings[0];

// The two rings (viz.tsx, Donut: radii 38 and 52 and a stroke of 9 on a box of 120),
// four times the size, in the corner the two lines leave free.
const CX = 1560;
const CY = 812;
const INNER = 152;
const OUTER = 208;
const STROKE = 36;

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
        const seen = Math.min(Math.max(drawn * round - start, 0), length - 5);
        if (seen <= 0) {
          return null;
        }
        const main = holding.symbol === bitcoin.symbol;
        return (
          <circle
            key={holding.symbol}
            cx={CX}
            cy={CY}
            r={radius}
            fill="none"
            stroke={TONE[holding.tone]}
            strokeOpacity={main ? 1 : 0.62}
            strokeWidth={STROKE}
            strokeDasharray={`${seen} ${round}`}
            strokeDashoffset={-start}
            style={
              main
                ? { filter: `drop-shadow(0 0 14px ${fade(C.btc, 0.55)})` }
                : undefined
            }
          />
        );
      })}
    </>
  );
};

/** A share as a hero number, counting up, with its words at headline size beside it. */
const Counted: React.FC<{
  readonly value: number;
  readonly words: string;
  readonly at: number;
  readonly colour: string;
  readonly top: number;
}> = ({ value, words, at, colour, top }) => {
  const frame = useCurrentFrame();
  const count = Math.round(tween(frame, at, at + 22, 0, value * 100, EASE));
  return (
    <div
      style={{
        position: "absolute",
        left: MARGIN - 8,
        top,
        display: "flex",
        alignItems: "baseline",
        gap: 40,
      }}
    >
      <div style={{ ...hero, color: colour }}>
        <Rise at={at}>{count}%</Rise>
      </div>
      <Headline lines={[words]} at={at + 4} />
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
      <Counted
        value={bitcoin.money}
        words={COPY.risk[0]}
        at={16}
        colour={C.ink}
        top={64}
      />
      <Counted
        value={bitcoin.risk}
        words={COPY.risk[1]}
        at={46}
        colour={C.btc}
        top={64 + HERO + 8}
      />

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
            gap: 12,
            fontSize: 34,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            color: C.ink,
          }}
        >
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: "50%",
              background: C.btc,
            }}
          />
          Bitcoin
        </div>
      </div>

      {/* viz.tsx, Legend, and what the two rings are. */}
      <div
        style={{
          position: "absolute",
          left: MARGIN,
          top: 842,
          fontFamily: FONT,
          opacity: names,
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 36,
            fontSize: 26,
            color: C.muted,
            whiteSpace: "nowrap",
          }}
        >
          {holdings.map((holding) => (
            <span
              key={holding.symbol}
              style={{ display: "flex", alignItems: "center", gap: 10 }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  background: TONE[holding.tone],
                }}
              />
              {holding.name}
            </span>
          ))}
        </div>
        <div style={{ ...label, fontSize: 20, marginTop: 18 }}>
          Inner ring: money · Outer ring: risk
        </div>
      </div>
      <ExampleNote opacity={names} />
    </AbsoluteFill>
  );
};
