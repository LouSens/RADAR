import { spring } from "remotion";
import { C } from "../theme";
import { FPS } from "../timing";
import { TONE, num } from "./kit";

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
