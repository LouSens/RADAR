import { spring } from "remotion";
import { C, darker, fade, lighter } from "../theme";
import { EASE, FPS, tween } from "../timing";
import { TONE, base, label as labelStyle, num } from "./kit";

/**
 * The app's elements as things that move: counted numbers, lines that draw on, chips
 * that pop, beads that slide. Every one is the app's own element (index.css, ui.tsx,
 * viz.tsx) and nothing here keeps time by itself: each takes the frame, or a value made
 * from it. Sizes are the app's own CSS pixels; a shot enlarges a piece with `zoom`.
 */

/** A small overshoot and settle, 0 before `at` and 1 once it has landed. */
export const pop = (frame: number, at: number, damping = 12): number =>
  spring({
    frame: frame - at,
    fps: FPS,
    config: { damping, mass: 0.5, stiffness: 190 },
  });

/** A landing with follow-through, for things that slide to a place. */
export const settle = (frame: number, at: number, damping = 13): number =>
  spring({
    frame: frame - at,
    fps: FPS,
    config: { damping, mass: 0.7, stiffness: 120 },
  });

/** Wraps a chip, pill or badge so that it pops in. */
export const Pop: React.FC<{
  readonly by: number;
  readonly origin?: string;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({ by, origin = "50% 50%", style, children }) => (
  <span
    style={{
      display: "inline-flex",
      scale: by,
      opacity: Math.min(Math.max(by * 3, 0), 1),
      transformOrigin: origin,
      ...style,
    }}
  >
    {children}
  </span>
);

const LINE = 1.15;

/** The name of the blur a turning wheel is given. The film draws it once (RollBlur). */
const ROLL_BLUR = "roll-blur";

/**
 * A blur up and down only, as tall as a share of what it is laid on, for the wheels of
 * a counting number. Drawn once, anywhere in the film.
 */
export const RollBlur: React.FC = () => (
  <svg width={0} height={0} style={{ position: "absolute" }}>
    <filter
      id={ROLL_BLUR}
      primitiveUnits="objectBoundingBox"
      x="-0.2"
      y="-0.2"
      width="1.4"
      height="1.4"
    >
      <feGaussianBlur stdDeviation="0 0.035" />
    </filter>
  </svg>
);

/**
 * A number that counts the way a meter does: every digit is a wheel, and a wheel turns
 * only while the wheels below it go from nine to nought. No digit jumps. Figures are
 * tabular, so the number keeps its width while it counts. `places` fixes how many
 * digits there are when the count passes a power of ten.
 */
export const Ticker: React.FC<{
  readonly value: number;
  readonly prefix?: string;
  readonly suffix?: string;
  readonly places?: number;
  readonly style?: React.CSSProperties;
}> = ({ value, prefix = "", suffix = "", places, style }) => {
  // All but there is there: a wheel is not left a hair off its figure.
  const near = Math.round(value);
  const amount = Math.max(Math.abs(value - near) < 0.015 ? near : value, 0);
  const whole = Math.floor(amount + 1e-9);
  const count = places ?? Math.max(String(whole).length, 1);
  const wheels: React.ReactNode[] = [];
  for (let k = count - 1; k >= 0; k--) {
    const unit = 10 ** k;
    const digit = Math.floor(amount / unit + 1e-9) % 10;
    // The lowest wheel turns all the time; the others only as those below roll over.
    const below = amount % unit;
    const turn = k === 0 ? amount - whole : Math.max(below - (unit - 1), 0);
    const hidden = k > 0 && amount < unit;
    wheels.push(
      <span
        key={k}
        style={{
          display: "inline-block",
          height: `${LINE}em`,
          overflow: "hidden",
          verticalAlign: "top",
          opacity: hidden ? 0 : 1,
          width: hidden && places === undefined ? 0 : undefined,
        }}
      >
        <span
          style={{
            display: "flex",
            flexDirection: "column",
            translate: `0 ${-turn * LINE}em`,
            // A wheel caught turning is blurred along its turn, as a moving thing is.
            filter:
              turn > 0.02 && turn < 0.98 ? `url(#${ROLL_BLUR})` : undefined,
          }}
        >
          <span style={{ height: `${LINE}em` }}>{digit}</span>
          <span style={{ height: `${LINE}em` }}>{(digit + 1) % 10}</span>
        </span>
      </span>,
    );
    if (k > 0 && k % 3 === 0) {
      wheels.push(
        <span key={`c${k}`} style={{ opacity: hidden ? 0 : 1 }}>
          ,
        </span>,
      );
    }
  }
  return (
    <span
      style={{
        ...num,
        display: "inline-flex",
        lineHeight: LINE,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {prefix}
      {wheels}
      {suffix}
    </span>
  );
};

/** A placeholder with the app's shimmer passing over it (components/Skeleton.tsx). */
export const Skeleton: React.FC<{
  readonly frame: number;
  readonly style?: React.CSSProperties;
}> = ({ frame, style }) => (
  <span
    style={{
      display: "block",
      borderRadius: 8,
      backgroundColor: "rgba(255,255,255,0.06)",
      backgroundImage:
        "linear-gradient(100deg, transparent 30%, rgba(255,255,255,0.09) 50%, transparent 70%)",
      backgroundSize: "200% 100%",
      backgroundPosition: `${130 - ((frame * 5) % 160)}% 0`,
      ...style,
    }}
  />
);

/**
 * Content that arrives the way the app's does: its placeholder first, then the real
 * thing in its place. `by` goes from 0 (placeholder) to 1 (content).
 */
export const Resolve: React.FC<{
  readonly by: number;
  readonly frame: number;
  readonly shape?: React.CSSProperties;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({ by, frame, shape, style, children }) => (
  <span style={{ position: "relative", display: "block", ...style }}>
    <span
      style={{
        display: "block",
        opacity: by,
        translate: `0 ${(1 - by) * 6}px`,
      }}
    >
      {children}
    </span>
    {by < 1 && (
      <Skeleton
        frame={frame}
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: "70%",
          height: "100%",
          opacity: 1 - by,
          ...shape,
        }}
      />
    )}
  </span>
);

/** How long the radar's ring takes to spread and go. */
export const PING = 20;

/** The radar's ring, spreading from the figure that answers the question. */
export const Ping: React.FC<{
  readonly since: number;
  readonly x: number;
  readonly y: number;
  readonly reach?: number;
}> = ({ since, x, y, reach = 170 }) => {
  if (since < 0 || since > PING) {
    return null;
  }
  const spread = tween(since, 0, PING, 0, 1, EASE);
  return (
    <>
      {[1, 0.55].map((part) => {
        const r = 14 + spread * reach * part;
        return (
          <span
            key={part}
            style={{
              position: "absolute",
              left: x - r,
              top: y - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              border: `${4 * part + 1.5}px solid ${C.accent}`,
              boxShadow: `0 0 28px ${fade(C.accent, 0.6)}, inset 0 0 28px ${fade(C.accent, 0.3)}`,
              opacity: 1 - spread * spread,
            }}
          />
        );
      })}
    </>
  );
};

/** The app's segmented control (.segmented), its pill sliding to the choice. */
export const Segmented: React.FC<{
  readonly options: readonly string[];
  /** Which option the pill is on; a value between two is the pill on its way. */
  readonly at: number;
}> = ({ options, at }) => {
  const wide = 62;
  return (
    <span
      style={{
        ...base,
        position: "relative",
        display: "inline-flex",
        padding: 3,
        borderRadius: 999,
        border: `1px solid ${C.line}`,
        background: "rgba(255,255,255,0.03)",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 3,
          bottom: 3,
          left: 3 + at * wide,
          width: wide,
          borderRadius: 999,
          background: "rgba(255,255,255,0.11)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.12)",
        }}
      />
      {options.map((option, i) => (
        <span
          key={option}
          style={{
            position: "relative",
            width: wide,
            textAlign: "center",
            fontSize: 12,
            fontWeight: 500,
            lineHeight: "24px",
            color: Math.abs(at - i) < 0.5 ? C.ink : C.muted,
          }}
        >
          {option}
        </span>
      ))}
    </span>
  );
};

/** A holding's colour as the app lays it on: lighter along the top, darker at the foot. */
const paint = (id: string, tone: string): React.ReactNode => (
  <linearGradient key={tone} id={`${id}-${tone}`} x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stopColor={lighter(TONE[tone])} />
    <stop offset="0.45" stopColor={TONE[tone]} />
    <stop offset="1" stopColor={darker(TONE[tone])} />
  </linearGradient>
);

export interface Share {
  readonly symbol: string;
  readonly tone: string;
  readonly share: number;
}

/**
 * One ring of the app's donut (viz.tsx, Donut), drawn clockwise from twelve o'clock.
 * Each holding is an arc with round ends in its own colour; cash is not drawn, so its
 * share is the track left showing. `drawn` says how far round each arc has swept, one
 * number a holding, and `swell` thickens one of them.
 */
export const DonutRing: React.FC<{
  readonly id: string;
  readonly radius: number;
  readonly width: number;
  readonly shares: readonly Share[];
  readonly drawn: readonly number[];
  readonly quiet?: boolean;
  readonly swell?: Readonly<Record<string, number>>;
}> = ({ id, radius, width, shares, drawn, quiet = false, swell = {} }) => {
  const round = 2 * Math.PI * radius;
  const gap = width + 1.2;
  let used = 0;
  return (
    <>
      <defs>{["btc", "gold", "stock"].map((tone) => paint(id, tone))}</defs>
      <circle
        cx="60"
        cy="60"
        r={radius}
        fill="none"
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={width}
      />
      {shares.map((part, i) => {
        const length = part.share * round;
        const start = used;
        used += length;
        const seen = (length - gap) * (drawn[i] ?? 0);
        if (part.tone === "cash" || seen <= 0.05) {
          return null;
        }
        return (
          <circle
            key={part.symbol}
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke={`url(#${id}-${part.tone})`}
            strokeOpacity={quiet ? 0.65 : 1}
            strokeWidth={width * (1 + (swell[part.symbol] ?? 0))}
            strokeLinecap="round"
            strokeDasharray={`${seen} ${round}`}
            strokeDashoffset={-(start + gap / 2)}
            transform="rotate(-90 60 60)"
          />
        );
      })}
    </>
  );
};

/** The app's small dot of a holding's colour (viz.tsx, Swatch). Cash is a ring. */
export const Swatch: React.FC<{
  readonly tone: string;
  readonly size?: number;
}> = ({ tone, size = 10 }) => (
  <span
    style={{
      display: "inline-block",
      width: size,
      height: size,
      borderRadius: "50%",
      boxSizing: "border-box",
      background: tone === "cash" ? "transparent" : TONE[tone],
      border: tone === "cash" ? `1.5px solid ${C.faint}` : undefined,
      flex: "none",
    }}
  />
);

/**
 * The app's range bar (CheckPanel.tsx): where a price sits between the lowest and the
 * highest of a period. `place` is where the bead is now, from 0 to 1.
 */
export const RangeBar: React.FC<{
  readonly name: string;
  readonly place: number;
  /** The figure beside it, counted with the bead. */
  readonly shown: number;
  readonly lit?: number;
  /** The words under the two ends of the bar. */
  readonly ends?: boolean;
}> = ({ name, place, shown, lit = 1, ends = true }) => (
  <div style={{ ...base, display: "flex", flexDirection: "column", gap: 5 }}>
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        fontSize: 14,
        lineHeight: 1.3,
      }}
    >
      <span style={{ fontWeight: 600 }}>{name}</span>
      <span style={{ color: C.muted, opacity: lit }}>
        <Ticker value={shown} places={2} /> out of 100
      </span>
    </div>
    <div
      style={{
        position: "relative",
        height: 8,
        borderRadius: 999,
        background: "rgba(255,255,255,0.08)",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: "50%",
          left: `${Math.min(Math.max(place, 0), 1.04) * 100}%`,
          width: 14,
          height: 14,
          translate: "-50% -50%",
          borderRadius: "50%",
          background: C.accent,
          border: `2px solid ${C.bg}`,
          boxSizing: "border-box",
          boxShadow: `0 0 ${10 * lit}px ${fade(C.accent, 0.55)}`,
          scale: 0.4 + 0.6 * lit,
          opacity: Math.min(lit * 2, 1),
        }}
      />
    </div>
    {ends && (
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 11,
          lineHeight: 1.3,
          color: C.faint,
        }}
      >
        <span>Lowest</span>
        <span>Highest</span>
      </div>
    )}
  </div>
);

/**
 * The app's plan bar (viz.tsx, StackBar): each holding a rounded piece in its colour,
 * and cash the track left unfilled.
 */
export const StackBar: React.FC<{
  readonly shares: readonly Share[];
  readonly height?: number;
}> = ({ shares, height = 8 }) => (
  <div
    style={{
      display: "flex",
      gap: 3,
      height,
      borderRadius: 999,
      background: "rgba(255,255,255,0.08)",
      overflow: "hidden",
    }}
  >
    {shares
      .filter((part) => part.tone !== "cash")
      .map((part) => (
        <span
          key={part.symbol}
          style={{
            width: `${part.share * 100}%`,
            borderRadius: 999,
            background: `linear-gradient(180deg, ${lighter(TONE[part.tone])} 0%, ${TONE[part.tone]} 45%, ${darker(TONE[part.tone])} 100%)`,
          }}
        />
      ))}
  </div>
);

/** A card's small heading (.label). */
export const Label: React.FC<{
  readonly children: React.ReactNode;
  readonly style?: React.CSSProperties;
}> = ({ children, style }) => (
  <span style={{ ...base, ...labelStyle, display: "block", ...style }}>
    {children}
  </span>
);
