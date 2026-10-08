import { AbsoluteFill, interpolateColors, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, fade } from "../theme";
import { COPY, EASE_IN_OUT, HEIGHT, tween } from "../timing";
import { Headline, MARGIN, Small, TOP, hero } from "../Type";
import { ExampleNote, TONE } from "../ui/kit";

const holdings = portfolio.holdings;
const bitcoin = holdings[0];

// One pair of rings, about four fifths of the frame's height, right of the words. The
// proportions are the app's (viz.tsx, Donut), opened up so that the number fits inside.
const CX = 1280;
const CY = HEIGHT / 2;
const INNER = 350;
const OUTER = 410;
const STROKE = 44;

/** When the money ring draws and the number counts to it, and the same for risk. */
export const MONEY = [14, 36] as const;
export const RISK = [50, 72] as const;

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
        const seen = Math.min(Math.max(drawn * round - start, 0), length - 7);
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
            strokeOpacity={main ? 1 : 0.6}
            strokeWidth={STROKE}
            strokeDasharray={`${seen} ${round}`}
            strokeDashoffset={-start}
            style={
              main
                ? { filter: `drop-shadow(0 0 18px ${fade(C.btc, 0.55)})` }
                : undefined
            }
          />
        );
      })}
    </>
  );
};

/**
 * Shot 6. One number, in the middle of its rings as the app puts it. The inner ring is
 * how the account's money is split and the number counts to Bitcoin's share of it; then
 * the outer ring, how its risk is split, draws round it and the same number counts on to
 * Bitcoin's share of that, turning amber. Figures: the made-up example in
 * fixtures/portfolio.json.
 */
export const Risk: React.FC = () => {
  const frame = useCurrentFrame();
  const money = tween(frame, MONEY[0], MONEY[1], 0, 1, EASE_IN_OUT);
  const risk = tween(frame, RISK[0], RISK[1], 0, 1, EASE_IN_OUT);
  const share = bitcoin.money * money + (bitcoin.risk - bitcoin.money) * risk;

  return (
    <AbsoluteFill>
      {/* The words change with the ring: the first pair leaves as the second ring starts. */}
      <Headline
        lines={COPY.risk.money}
        at={MONEY[0] - 2}
        out={RISK[0] - 2}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />
      <Headline
        lines={COPY.risk.risk}
        at={RISK[0] + 6}
        accent={C.btc}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
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

      {/* Whose share it is, and the share. */}
      <Small
        at={MONEY[0]}
        colour={C.ink}
        text={
          <span style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: C.btc,
              }}
            />
            Bitcoin
          </span>
        }
        style={{
          position: "absolute",
          left: CX,
          top: CY - 196,
          translate: "-50% 0",
        }}
      />
      <div
        style={{
          ...hero,
          position: "absolute",
          left: CX,
          top: CY + 14,
          translate: "-50% -50%",
          color: interpolateColors(risk, [0, 1], [C.ink, C.btc]),
        }}
      >
        {Math.round(share * 100)}%
      </div>
      <ExampleNote />
    </AbsoluteFill>
  );
};
