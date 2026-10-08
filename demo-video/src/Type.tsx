import { useCurrentFrame } from "remotion";
import { C, FEATURES, FONT, NUM_FEATURES } from "./theme";
import { BEAT, EASE, EASE_IN_OUT, tween } from "./timing";

/**
 * The film's type, all of it. Three sizes and nothing else: a headline, a hero number
 * and a small line. One grid: headlines start at the left margin, in the upper third.
 * Type never fades and is never blurred. Each piece rises out of a mask at the foot of
 * its line, and leaves by rising out through the top of it.
 */
export const HEADLINE = 140;
export const HERO = 260;
export const SMALL = 40;
/** The end card's second line, and the only place this size is used. */
export const END_LINE = 80;
export const MARGIN = 128;
export const TOP = 96;
/** How tall a line of headline is. */
export const LINE = HEADLINE * 1.05;

/** How long a piece takes to rise into place, or out. */
const RISE = 8;
/** Words arrive half a beat apart unless a shot says a whole one. */
const HALF = BEAT / 2;

/**
 * One piece of type behind its own mask. The mask is a little larger than the line, so
 * descenders and tight letters are not shaved while the piece stands still.
 */
export const Rise: React.FC<{
  readonly at: number;
  readonly out?: number;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({ at, out, style, children }) => {
  const frame = useCurrentFrame();
  const up = tween(frame, at, at + RISE, 130, 0, EASE);
  const gone =
    out === undefined ? 0 : tween(frame, out, out + RISE, 0, -130, EASE_IN_OUT);
  return (
    <span
      style={{
        display: "inline-block",
        overflow: "hidden",
        verticalAlign: "top",
        padding: "0.1em 0.07em 0.22em",
        margin: "-0.1em -0.07em -0.22em",
      }}
    >
      <span
        style={{
          display: "inline-block",
          translate: `0 ${up + gone}%`,
          ...style,
        }}
      >
        {children}
      </span>
    </span>
  );
};

/**
 * A headline: Inter Bold at 140 with tracking of -3%, a word at a time. Words between
 * asterisks take the accent colour: "Meet *RADAR.*". Each string is a line.
 */
export const Headline: React.FC<{
  readonly lines: readonly string[];
  /** The frame the first word starts to rise. */
  readonly at: number;
  /** Where a line starts, if not straight after the line before. */
  readonly lineAt?: readonly (number | undefined)[];
  /** Frames between words. */
  readonly step?: number;
  /** The frame every word starts to leave, together. */
  readonly out?: number;
  readonly accent?: string;
  readonly style?: React.CSSProperties;
}> = ({ lines, at, lineAt, step = HALF, out, accent = C.accent, style }) => {
  let next = at;
  let lit = false;
  return (
    <div
      style={{
        fontFamily: FONT,
        fontFeatureSettings: FEATURES,
        fontSize: HEADLINE,
        fontWeight: 700,
        letterSpacing: "-0.03em",
        lineHeight: 1.05,
        color: C.ink,
        ...style,
      }}
    >
      {lines.map((line, row) => {
        next = lineAt?.[row] ?? next;
        const start = next;
        const words = line.split(" ");
        next = start + words.length * step;
        return (
          <div
            key={line + row}
            style={{ display: "flex", gap: "0.24em", whiteSpace: "nowrap" }}
          >
            {words.map((raw, i) => {
              const marked = lit || raw.startsWith("*");
              lit = marked && !raw.endsWith("*");
              return (
                <Rise
                  key={raw + i}
                  at={Math.round(start + i * step)}
                  out={out}
                  style={{ color: marked ? accent : undefined }}
                >
                  {raw.split("*").join("")}
                </Rise>
              );
            })}
          </div>
        );
      })}
    </div>
  );
};

/** The small line: Inter Medium at 40, in the muted grey. It rises as one piece. */
export const Small: React.FC<{
  readonly text: React.ReactNode;
  readonly at: number;
  readonly out?: number;
  readonly colour?: string;
  readonly style?: React.CSSProperties;
}> = ({ text, at, out, colour = C.muted, style }) => (
  <div
    style={{
      fontFamily: FONT,
      fontFeatureSettings: FEATURES,
      fontSize: SMALL,
      fontWeight: 500,
      letterSpacing: "-0.011em",
      lineHeight: 1.2,
      whiteSpace: "nowrap",
      color: colour,
      ...style,
    }}
  >
    <Rise at={at} out={out}>
      {text}
    </Rise>
  </div>
);

/** A hero number: 260, with every digit the same width so that a count does not shake. */
export const hero: React.CSSProperties = {
  fontFamily: FONT,
  fontFeatureSettings: NUM_FEATURES,
  fontVariantNumeric: "tabular-nums",
  fontSize: HERO,
  fontWeight: 600,
  letterSpacing: "-0.04em",
  lineHeight: 1,
  whiteSpace: "nowrap",
  color: C.ink,
};
