import { C, FEATURES, FONT, NUM_FEATURES, fade } from "../theme";

/**
 * The app's interface, rebuilt for the film from frontend/src (index.css, ui.tsx,
 * viz.tsx, MarketCard.tsx, StepsPanel.tsx, Layout.tsx). Sizes are the app's own CSS
 * pixels; a shot enlarges a piece with `zoom`. Nothing here moves by itself: every
 * animated value is a prop, set from the frame.
 */

export const TONE: Readonly<Record<string, string>> = {
  btc: C.btc,
  gold: C.gold,
  stock: C.stock,
  accent: C.accent,
  cash: "rgba(255,255,255,0.28)",
};

/** viz.tsx, STATE_COLOUR. */
const STATE_COLOUR: Readonly<Record<string, string>> = {
  calm: C.calm,
  normal: C.muted,
  elevated: C.gold,
  turbulent: C.alert,
};
export const stateColour = (label: string): string =>
  STATE_COLOUR[label] ?? C.accent;

/** lib/format.ts. */
export const formatPrice = (value: number): string => {
  const digits = value >= 1000 ? 0 : value >= 10 ? 2 : 4;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
};

export const formatMoney = (value: number): string => {
  const digits = Math.abs(value) >= 1000 ? 0 : 2;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
};

export const base: React.CSSProperties = {
  fontFamily: FONT,
  fontFeatureSettings: FEATURES,
  fontOpticalSizing: "auto",
  letterSpacing: "-0.011em",
  lineHeight: 1.6,
  color: C.ink,
  WebkitFontSmoothing: "antialiased",
};

/** .num */
export const num: React.CSSProperties = {
  fontVariantNumeric: "tabular-nums",
  fontFeatureSettings: NUM_FEATURES,
  letterSpacing: "-0.02em",
};

/** .label */
export const label: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.075em",
  textTransform: "uppercase",
  color: C.muted,
  lineHeight: 1.6,
};

/** .glass: one pane, lit from above. */
export const glass: React.CSSProperties = {
  position: "relative",
  background:
    "linear-gradient(180deg, rgba(255,255,255,0.065), rgba(255,255,255,0.022))",
  border: "1px solid rgba(255,255,255,0.085)",
  borderRadius: 20,
  boxShadow:
    "inset 0 1px 0 rgba(255,255,255,0.09), 0 20px 44px -28px rgba(0,0,0,0.75)",
};

/** .glass::before: the thin highlight along a card's top edge. */
export const TopEdge: React.FC = () => (
  <span
    style={{
      position: "absolute",
      top: 0,
      left: "12%",
      right: "12%",
      height: 1,
      background:
        "linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent)",
    }}
  />
);

/** .tile.toned: a market's card, with a breath of its own colour in the corner. */
export const toned = (tone: string): React.CSSProperties => ({
  background: `radial-gradient(90% 130% at 0% 0%, ${fade(tone, 0.16)}, transparent 62%), linear-gradient(180deg, rgba(255,255,255,0.065), rgba(255,255,255,0.022))`,
  border: "1px solid rgba(255,255,255,0.085)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.09)",
});

/** lib/stats.ts, sparklinePath. */
const sparklinePath = (
  values: readonly number[],
  width: number,
  height: number,
  pad = 2,
): string => {
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  return values
    .map((value, i) => {
      const x = pad + (i / (values.length - 1)) * (width - 2 * pad);
      const y = height - pad - ((value - low) / span) * (height - 2 * pad);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
};

/** ui.tsx, Sparkline. `drawn` uncovers it from the left, from 0 to 1. */
export const Sparkline: React.FC<{
  readonly id: string;
  readonly values: readonly number[];
  readonly colour: string;
  readonly drawn?: number;
  /** Without it only the fill under the line is drawn. */
  readonly line?: boolean;
}> = ({ id, values, colour, drawn = 1, line = true }) => {
  const width = 120;
  const height = 36;
  const path = sparklinePath(values, width, height);
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block", width: "100%", height: "100%" }}
    >
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={colour} stopOpacity="0.28" />
          <stop offset="1" stopColor={colour} stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <rect x="0" y="0" width={width * drawn} height={height} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id}-clip)`}>
        <path
          d={`${path} L${width},${height} L0,${height} Z`}
          fill={`url(#${id}-fill)`}
        />
        <path
          d={path}
          fill="none"
          stroke={colour}
          strokeOpacity={line ? 1 : 0}
          strokeWidth="1.6"
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </g>
    </svg>
  );
};

/** ui.tsx, Change. The input is a fraction. */
export const Change: React.FC<{
  readonly value: number;
  readonly style?: React.CSSProperties;
}> = ({ value, style }) => {
  const up = value >= 0;
  return (
    <span
      style={{
        ...num,
        whiteSpace: "nowrap",
        color: up ? C.calm : C.alert,
        ...style,
      }}
    >
      {up ? "▲" : "▼"} {Math.abs(value * 100).toFixed(2)}%
    </span>
  );
};

export interface Market {
  readonly slug: string;
  readonly name: string;
  readonly tone: string;
  readonly price: number;
  readonly sinceClose: number;
  readonly weekCloses: readonly number[];
  readonly state: string;
}

/**
 * MarketCard.tsx. `wide` is the card as it is laid out with room (its @2xl sizes); the
 * default is the phone's. `drawn` uncovers the week's line and `stated` brings the state
 * word on.
 */
export const MarketCard: React.FC<{
  readonly market: Market;
  readonly wide?: boolean;
  readonly drawn?: number;
  readonly stated?: number;
  /** Whether the week's line is drawn over its fill. */
  readonly line?: boolean;
  /** Tells two copies of one card apart, so their drawings do not share names. */
  readonly copy?: string;
  readonly style?: React.CSSProperties;
}> = ({
  market,
  wide = false,
  drawn = 1,
  stated = 1,
  line = true,
  copy = "",
  style,
}) => {
  const tone = TONE[market.tone];
  return (
    <div
      style={{
        ...base,
        ...toned(tone),
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        padding: wide ? "17.6px 19.2px 19.2px" : "11.2px 11.2px 10.4px",
        borderRadius: wide ? 18 : 16,
        ...style,
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{ width: 8, height: 8, borderRadius: "50%", background: tone }}
        />
        <span
          style={{
            fontSize: wide ? 14 : 13,
            fontWeight: 500,
            lineHeight: 1.45,
            whiteSpace: "nowrap",
          }}
        >
          {market.name}
        </span>
      </span>
      <span
        style={{
          ...num,
          marginTop: 8,
          fontSize: wide ? 22.4 : 16.3,
          fontWeight: 600,
          lineHeight: 1.25,
          letterSpacing: "-0.025em",
        }}
      >
        {formatPrice(market.price)}
      </span>
      <Change
        value={market.sinceClose}
        style={{ marginTop: 2, fontSize: wide ? 14 : 12, lineHeight: 1.4 }}
      />
      <span style={{ display: "block", marginTop: 8, height: wide ? 44 : 32 }}>
        <Sparkline
          id={`spark-${market.slug}-${wide ? "w" : "p"}${copy}`}
          values={market.weekCloses}
          colour={tone}
          drawn={drawn}
          line={line}
        />
      </span>
      <span
        style={{
          marginTop: 8,
          fontSize: wide ? 12 : 11,
          fontWeight: 500,
          lineHeight: 1.4,
          textTransform: "capitalize",
          color: stateColour(market.state),
          opacity: Math.min(stated * 1.5, 1),
          scale: 0.6 + 0.4 * stated,
          transformOrigin: "0 50%",
        }}
      >
        {market.state}
      </span>
    </div>
  );
};

/** Layout.tsx, RadarMark: the app's badge. */
export const RadarMark: React.FC<{ readonly size?: number }> = ({
  size = 30,
}) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
    <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="9" fill="#0d1820" />
    <rect
      x="0.75"
      y="0.75"
      width="30.5"
      height="30.5"
      rx="9"
      stroke={C.accent}
      strokeOpacity="0.4"
      strokeWidth="1.5"
    />
    <circle
      cx="15"
      cy="17"
      r="8.5"
      stroke={C.accent}
      strokeOpacity="0.35"
      strokeWidth="1.5"
    />
    <path
      d="M7.5 21.5 12.5 16.5l3.5 3 8.5-9.5"
      stroke={C.accent}
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="24.5" cy="10" r="2.4" fill={C.accent} />
  </svg>
);

export const Stroke: React.FC<{ readonly children: React.ReactNode }> = ({
  children,
}) => (
  <svg
    width="22"
    height="22"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ flex: "none" }}
  >
    {children}
  </svg>
);

/** Layout.tsx: the five places and their icons. */
export const PLACES = [
  {
    label: "Home",
    icon: (
      <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1v-7.5Z" />
    ),
  },
  {
    label: "Markets",
    icon: (
      <>
        <circle cx="9" cy="12" r="5.5" />
        <circle cx="15" cy="12" r="5.5" />
      </>
    ),
  },
  {
    label: "Portfolio",
    icon: (
      <>
        <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5H12V3.5Z" />
        <path d="M15.5 3.6a8.5 8.5 0 0 1 4.9 4.9h-4.9V3.6Z" />
      </>
    ),
  },
  {
    label: "Signals",
    icon: (
      <>
        <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15l1.5-2Z" />
        <path d="M10 20.5a2 2 0 0 0 4 0" />
      </>
    ),
  },
  {
    label: "Calendar",
    icon: (
      <>
        <rect x="4" y="5.5" width="16" height="14" rx="2.5" />
        <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
      </>
    ),
  },
] as const;

/** The phone's bar (Layout.tsx and .bar-tab in index.css), with one place lit. */
export const TabBar: React.FC<{
  readonly here: (typeof PLACES)[number]["label"];
  readonly tint?: string;
}> = ({ here, tint = C.accent }) => (
  <div
    style={{
      ...base,
      display: "flex",
      gap: 4,
      padding: 6,
      borderRadius: 999,
      border: "1px solid rgba(255,255,255,0.13)",
      background:
        "linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02)), #111218",
      boxShadow:
        "0 10px 30px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.1)",
    }}
  >
    {PLACES.map((place) => {
      const on = place.label === here;
      return (
        <span
          key={place.label}
          style={{
            display: "flex",
            flex: `${on ? 2.2 : 1} 1 0%`,
            minWidth: 0,
            height: 44,
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 999,
            color: on ? C.ink : C.muted,
            background: on
              ? `color-mix(in srgb, ${tint} 16%, rgba(255,255,255,0.05))`
              : "transparent",
            boxShadow: on ? `inset 0 0 0 1px ${fade(tint, 0.34)}` : undefined,
          }}
        >
          <Stroke>{place.icon}</Stroke>
          {on && (
            <span style={{ marginLeft: 8, fontSize: 13, fontWeight: 600 }}>
              {place.label}
            </span>
          )}
        </span>
      );
    })}
  </div>
);

export interface Rung {
  readonly price: number;
  readonly amount: number;
  readonly below: number;
}

/**
 * StepsPanel.tsx, Ladder: the purchase as steps down a price line, today's price on the
 * right. `lit` is how far along each dot is in lighting up, one number a rung.
 */
export const Ladder: React.FC<{
  readonly rungs: readonly Rung[];
  readonly lit?: readonly number[];
  /** A blip flying in to each dot: its colour and how far it has flown, from 0 to 1. */
  readonly blips?: readonly {
    readonly colour: string;
    readonly flown: number;
  }[];
}> = ({ rungs, lit, blips }) => {
  const deepest = Math.max(...rungs.map((r) => r.below), 0);
  const at = (below: number): number =>
    deepest > 0 ? 100 - (below / deepest) * 84 : 50;
  const last = rungs.length - 1;
  return (
    <div style={base}>
      <div style={{ position: "relative", height: 56 }}>
        <span
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "50%",
            height: 1,
            background: C.lineStrong,
          }}
        />
        {rungs.map((rung, i) => (
          <span
            key={rung.price}
            style={{
              position: "absolute",
              top: 0,
              left: `${at(rung.below)}%`,
              height: "100%",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              alignItems:
                i === 0 ? "flex-end" : i === last ? "flex-start" : "center",
              translate: i === 0 ? "-100% 0" : i === last ? "0 0" : "-50% 0",
            }}
          >
            <span
              style={{
                ...num,
                whiteSpace: "nowrap",
                fontSize: 12,
                lineHeight: 1.35,
                color: C.muted,
              }}
            >
              {i === 0 ? "now " : ""}
              {formatPrice(rung.price)}
            </span>
            <span
              style={{
                ...num,
                whiteSpace: "nowrap",
                fontSize: 14,
                fontWeight: 600,
                lineHeight: 1.35,
              }}
            >
              {formatMoney(rung.amount)}
            </span>
          </span>
        ))}
        {rungs.map((rung, i) => {
          // In the app the first dot is filled and the rest are rings. In the film a
          // dot fills as it lights.
          const on = lit ? lit[i] : i === 0 ? 1 : 0;
          return (
            <span
              key={`dot-${rung.price}`}
              style={{
                position: "absolute",
                top: "50%",
                left: `${at(rung.below)}%`,
                width: 12,
                height: 12,
                translate: "-50% -50%",
                borderRadius: "50%",
                boxSizing: "border-box",
                border: `2px solid ${C.accent}`,
                background: on > 0.5 ? C.accent : C.bg,
                scale: 1 + 0.5 * Math.sin(Math.min(on, 1) * Math.PI),
                boxShadow:
                  on > 0
                    ? `0 0 ${10 * Math.min(on, 1)}px ${2 * Math.min(on, 1)}px ${fade(C.accent, 0.55)}`
                    : undefined,
              }}
            />
          );
        })}
        {blips?.map((blip, i) => {
          const rung = rungs[i];
          if (!rung || blip.flown <= 0 || blip.flown >= 1) {
            return null;
          }
          // Each comes down out of the frame above on a curve of its own, shrinking to
          // the size of the dot it lands on.
          const left = 1 - blip.flown;
          const dx = (i - 1) * -150 * left;
          const dy = -230 * left * left - 40 * left;
          const size = 12 + 16 * left;
          return (
            <span
              key={`blip-${rung.price}`}
              style={{
                position: "absolute",
                top: "50%",
                left: `${at(rung.below)}%`,
                width: size,
                height: size,
                translate: `calc(-50% + ${dx}px) calc(-50% + ${dy}px)`,
                borderRadius: "50%",
                background: blip.colour,
                boxShadow: `0 0 ${14}px ${5}px ${fade(blip.colour, 0.45)}`,
              }}
            />
          );
        })}
      </div>
      {rungs.length > 1 && (
        <div
          style={{
            marginTop: 4,
            display: "flex",
            justifyContent: "space-between",
            fontSize: 12,
            lineHeight: 1.35,
            color: C.faint,
          }}
        >
          <span>← buy more if it falls</span>
          <span>today</span>
        </div>
      )}
    </div>
  );
};

/** ui.tsx, TrustBadge. */
export const TrustBadge: React.FC<{ readonly word: string }> = ({ word }) => (
  <span
    style={{
      ...base,
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "2px 8px",
      borderRadius: 999,
      border: `1px solid ${C.line}`,
      fontSize: 12,
      fontWeight: 500,
      color: C.muted,
      textTransform: "capitalize",
    }}
  >
    <span
      style={{ width: 6, height: 6, borderRadius: "50%", background: C.calm }}
    />
    {word}
  </span>
);

/** The small notice that a shot's figures are an example, not anyone's account. */
export const ExampleNote: React.FC<{
  readonly opacity?: number;
  readonly style?: React.CSSProperties;
}> = ({ opacity = 1, style }) => (
  <div
    style={{
      ...label,
      fontFamily: FONT,
      position: "absolute",
      left: 128,
      bottom: 48,
      fontSize: 34,
      display: "flex",
      alignItems: "center",
      gap: 12,
      opacity,
      ...style,
    }}
  >
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: C.faint,
      }}
    />
    Example portfolio
  </div>
);
