import { AbsoluteFill } from "remotion";
import market from "../fixtures/market.json";
import portfolio from "../fixtures/portfolio.json";
import { C, fade } from "../theme";
import {
  Ladder,
  MarketCard,
  RadarMark,
  TabBar,
  TopEdge,
  base,
  formatMoney,
  glass,
  label,
  num,
} from "./kit";

/** viz.tsx, LEVEL_COLOUR. */
const LEVEL_COLOUR: Readonly<Record<string, string>> = {
  low: C.calm,
  moderate: C.accent,
  high: C.gold,
  "very high": C.alert,
};

/** Overview.tsx, ACTIONS. */
const ACTIONS = [
  {
    label: "My risk",
    icon: (
      <>
        <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5H12V3.5Z" />
        <path d="M15.5 3.6a8.5 8.5 0 0 1 4.9 4.9h-4.9V3.6Z" />
      </>
    ),
  },
  {
    label: "Before I buy",
    icon: (
      <>
        <path d="M3.5 12h5" />
        <path d="M8.5 12 20.5 5.5M8.5 12l12 6.5" />
      </>
    ),
  },
  {
    label: "My plan",
    icon: (
      <>
        <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
        <circle cx="16" cy="7" r="2" />
        <circle cx="8" cy="17" r="2" />
      </>
    ),
  },
  {
    label: "My trades",
    icon: <path d="M4.5 19.5V15M9.5 19.5v-7.5M14.5 19.5V9M19.5 19.5v-15" />,
  },
] as const;

const { step } = portfolio;
const level = portfolio.riskLevel.label;

/**
 * The app's Home at phone size (pages/Overview.tsx), showing the example portfolio the
 * way the app itself shows one: labelled as an example. Photographed for the phone's
 * screen with `npx remotion still Home public/ui/home.png --scale=3`. The date is the
 * day the market figures were read.
 */
export const Home: React.FC = () => (
  <AbsoluteFill style={{ ...base, backgroundColor: C.bg, fontSize: 15 }}>
    {/* body::before and body::after: the window's light and its grid of points. */}
    <AbsoluteFill
      style={{
        background: `radial-gradient(110% 55% at 50% -12%, ${fade(C.accent, 0.26)}, transparent 62%), radial-gradient(50% 38% at 100% 0%, ${fade(C.accent, 0.12)}, transparent 70%)`,
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px) 0 0 / 22px 22px",
        maskImage: "linear-gradient(to bottom, #000 0%, transparent 46%)",
        WebkitMaskImage: "linear-gradient(to bottom, #000 0%, transparent 46%)",
      }}
    />

    <div
      style={{
        position: "absolute",
        inset: 0,
        padding: "24px 16px 0",
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <RadarMark size={26} />
          <span
            style={{ fontSize: 15, fontWeight: 600, letterSpacing: "0.12em" }}
          >
            RADAR
          </span>
        </span>
        <span style={label}>Thursday 8 October</span>
      </header>

      <section style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div>
          <span style={{ ...label, display: "block" }}>Example portfolio</span>
          <span
            style={{
              ...num,
              display: "block",
              marginTop: 6,
              fontSize: 34.9,
              fontWeight: 600,
              letterSpacing: "-0.04em",
              lineHeight: 1,
            }}
          >
            {formatMoney(portfolio.value)}
          </span>
          <span
            style={{
              marginTop: 8,
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 14,
              color: C.muted,
            }}
          >
            <span
              style={{
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 500,
                textTransform: "capitalize",
                color: LEVEL_COLOUR[level],
                background: fade(LEVEL_COLOUR[level], 0.15),
              }}
            >
              {level} risk
            </span>
            <span style={num}>
              ±{formatMoney(portfolio.typicalDay)} on a typical day
            </span>
          </span>
        </div>
        <p style={{ margin: "-8px 0 0", fontSize: 14, color: C.muted }}>
          These are made-up holdings.{" "}
          <span
            style={{
              fontWeight: 500,
              color: C.ink,
              textDecoration: "underline",
              textUnderlineOffset: 4,
            }}
          >
            Use my own
          </span>
        </p>
        <nav
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
            gap: 8,
          }}
        >
          {ACTIONS.map((action) => (
            <span
              key={action.label}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 7,
                color: C.muted,
              }}
            >
              <span
                style={{
                  display: "grid",
                  placeItems: "center",
                  width: 48,
                  height: 48,
                  borderRadius: 16,
                  color: C.ink,
                  background:
                    "linear-gradient(180deg, rgba(255,255,255,0.09), rgba(255,255,255,0.03))",
                  border: "1px solid rgba(255,255,255,0.1)",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.1)",
                }}
              >
                <svg
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {action.icon}
                </svg>
              </span>
              <span style={{ fontSize: 11, fontWeight: 500, lineHeight: 1.25 }}>
                {action.label}
              </span>
            </span>
          ))}
        </nav>
      </section>

      {/* StepsPanel.tsx, StepsCard: the things-to-do row. */}
      <div style={{ ...glass, padding: 16 }}>
        <TopEdge />
        <p style={{ ...label, margin: 0 }}>What to do now</p>
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 18,
            fontWeight: 600,
            letterSpacing: "-0.025em",
            lineHeight: 1.4,
          }}
        >
          Buy {formatMoney(step.amount)} of {step.name}
        </p>
        <div style={{ marginTop: 16 }}>
          <Ladder rungs={step.rungs} />
        </div>
        <p style={{ margin: "12px 0 0", fontSize: 14, color: C.muted }}>
          See every price and the reasons
        </p>
      </div>

      <section>
        <div
          style={{
            marginBottom: 10,
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.025em" }}
          >
            Markets
          </span>
          <span style={{ fontSize: 14, fontWeight: 500, color: C.muted }}>
            Compare
          </span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: 8,
          }}
        >
          {market.markets.map((m) => (
            <MarketCard key={m.slug} market={m} />
          ))}
        </div>
      </section>
    </div>

    <div style={{ position: "absolute", left: 12, right: 12, bottom: 12 }}>
      <TabBar here="Home" />
    </div>
  </AbsoluteFill>
);
