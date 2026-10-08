import { AbsoluteFill, interpolateColors, useCurrentFrame } from "remotion";
import { ASKED, OPENS, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C } from "../theme";
import { EASE_IN_OUT, shot, tween } from "../timing";
import { Rise } from "../Type";
import { BUTTON, type Box } from "../ui/Desk";
import { base, formatMoney, label } from "../ui/kit";
import { DonutRing, Ping, Swatch, Ticker, pop, settle } from "../ui/motion";

const { holdings } = film.portfolio;
const bitcoin = holdings[0];
const MONEY_SHARE = Math.round(bitcoin.money * 100);
const RISK_SHARE = Math.round(bitcoin.risk * 100);

/** The answer's frame: a little taller than usual, so the rings can be 70% of the
 *  frame's height. */
const AREA: Box = { x: 128, y: 214, w: 1664, h: 826 };
/** The rings, in the app's pixels: 378 across, which is 756 in the frame. */
const RINGS = { x: 26, y: 17, size: 378 } as const;
const TABLE = { x: 462, y: 104, w: 342, row: 54 } as const;

/** When the inner ring (money) sweeps in, and the number counts to it. */
export const MONEY = [ASKED + OPENS - 4, ASKED + OPENS + 14] as const;
/** When the outer ring (risk) sweeps in, and the number counts on. */
export const RISK = [ASKED + 40, ASKED + 58] as const;
/** When Bitcoin's piece of the outer ring swells. */
export const SWELL = RISK[1] - 4;
/** When the first row of the table slides in, and how long after it each other does. */
export const ROWS = ASKED + OPENS + 2;
export const EVERY = 4;
export const PINGED = RISK[1] + 4;

/**
 * Shot 6. The app's two rings, large. The inner ring is how the account's money is
 * split, and the number in the middle counts to Bitcoin's share of it; then the outer
 * ring, how its risk is split, sweeps in round it, Bitcoin's piece swells, and the same
 * number counts on to Bitcoin's share of that, in Bitcoin's colour. Beside them the
 * app's own rows arrive one by one. Figures: the made-up example portfolio
 * (fixtures/film.json).
 */
export const Risk: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("risk").duration;
  const money = tween(frame, MONEY[0], MONEY[1], 0, 1, EASE_IN_OUT);
  const risk = tween(frame, RISK[0], RISK[1], 0, 1, EASE_IN_OUT);
  const share = MONEY_SHARE * money + (RISK_SHARE - MONEY_SHARE) * risk;
  // A swell that goes a little too far and comes back to a thicker piece.
  const swell = settle(frame, SWELL, 9) * 0.32;
  const shares = (of: "money" | "risk") =>
    holdings.map((h) => ({ symbol: h.symbol, tone: h.tone, share: h[of] }));
  // Each piece of a ring sweeps in a little after the one before it.
  const swept = (start: number): number[] =>
    holdings.map((_, i) =>
      tween(frame, start + i * 3, start + 12 + i * 3, 0, 1, EASE_IN_OUT),
    );

  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={BUTTON.risk}
        area={AREA}
        card
        framed={ASKED + OPENS - 4}
        title=""
      >
        <svg
          viewBox="0 0 120 120"
          width={RINGS.size}
          height={RINGS.size}
          style={{ position: "absolute", left: RINGS.x, top: RINGS.y }}
        >
          <DonutRing
            id="risk-inner"
            radius={42}
            width={3.4}
            quiet
            shares={shares("money")}
            drawn={swept(MONEY[0])}
          />
          <DonutRing
            id="risk-outer"
            radius={52}
            width={5.6}
            shares={shares("risk")}
            drawn={swept(RISK[0])}
            swell={{ [bitcoin.symbol]: swell }}
          />
        </svg>
        {/* One number, in the middle of its rings as the app puts it. */}
        <div
          style={{
            ...base,
            position: "absolute",
            left: RINGS.x,
            top: RINGS.y,
            width: RINGS.size,
            height: RINGS.size,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              fontSize: 104,
              fontWeight: 600,
              letterSpacing: "-0.04em",
              color: interpolateColors(risk, [0, 1], [C.ink, C.btc]),
              opacity: frame >= MONEY[0] ? 1 : 0,
            }}
          >
            <Ticker value={share} suffix="%" places={2} />
          </span>
          <span
            style={{
              position: "relative",
              height: 34,
              width: "100%",
              fontSize: 24,
              fontWeight: 500,
            }}
          >
            <span
              style={{
                position: "absolute",
                inset: 0,
                textAlign: "center",
                color: C.muted,
              }}
            >
              <Rise at={MONEY[0] + 2} out={RISK[0] - 2}>
                of your money
              </Rise>
            </span>
            <span
              style={{
                position: "absolute",
                inset: 0,
                textAlign: "center",
                color: C.btc,
              }}
            >
              <Rise at={RISK[0] + 6}>of your risk</Rise>
            </span>
          </span>
        </div>

        {/* The app's own rows: each holding's share of the money, and of the risk. */}
        <div
          style={{
            ...base,
            position: "absolute",
            left: TABLE.x,
            top: TABLE.y,
            width: TABLE.w,
          }}
        >
          <div
            style={{
              ...label,
              display: "flex",
              justifyContent: "flex-end",
              gap: 38,
              height: 30,
              opacity: pop(frame, ROWS - 2),
            }}
          >
            <span>Money</span>
            <span>Risk</span>
          </div>
          {holdings.map((holding, i) => {
            const at = ROWS + i * EVERY;
            const slid = settle(frame, at, 14);
            const counted = tween(frame, at, at + 14, 0, 1, EASE_IN_OUT);
            const from = RISK[0] + i * 3;
            const risked = tween(frame, from, from + 16, 0, 1, EASE_IN_OUT);
            return (
              <div
                key={holding.symbol}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  height: TABLE.row,
                  borderTop: `1px solid ${C.line}`,
                  fontSize: 22,
                  translate: `${(1 - slid) * 70}px 0`,
                  opacity: Math.min(Math.max(slid * 2, 0), 1),
                }}
              >
                <Swatch tone={holding.tone} size={12} />
                <span style={{ fontWeight: 500 }}>{holding.name}</span>
                <span
                  style={{
                    marginLeft: "auto",
                    width: 64,
                    textAlign: "right",
                    color: C.muted,
                  }}
                >
                  <Ticker
                    value={Math.round(holding.money * 100) * counted}
                    suffix="%"
                  />
                </span>
                <span
                  style={{ width: 70, textAlign: "right", fontWeight: 700 }}
                >
                  {frame >= from && (
                    <Ticker
                      value={Math.round(holding.risk * 100) * risked}
                      suffix="%"
                    />
                  )}
                </span>
              </div>
            );
          })}
          <div
            style={{
              ...label,
              marginTop: 16,
              display: "flex",
              alignItems: "center",
              gap: 8,
              opacity: pop(frame, ROWS + 16),
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: C.faint,
              }}
            />
            Example portfolio · {formatMoney(film.portfolio.value)}
          </div>
        </div>
        <div style={{ ...label, position: "absolute", left: TABLE.x, top: 44 }}>
          <Rise at={ROWS - 4}>Your money, and where the risk sits</Rise>
        </div>
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + (TABLE.x + TABLE.w - 30) * ZOOM}
        y={AREA.y + (TABLE.y + 30 + TABLE.row / 2) * ZOOM}
      />
    </AbsoluteFill>
  );
};
