import { useCurrentFrame } from "remotion";
import { C, FEATURES, FONT } from "./theme";
import { EASE, tween } from "./timing";

/**
 * A line of type that arrives a word at a time, each word settling out of a blur.
 * Words between asterisks take the one accent colour: "Meet *RADAR.*".
 *
 * The line is laid out in full from its first frame, so nothing shifts as words appear.
 */
export const Words: React.FC<{
  readonly text: string;
  /** The frame the first word starts to arrive. */
  readonly at: number;
  /** The frame the line starts to leave; it stays if this is not given. */
  readonly out?: number;
  readonly size: number;
  readonly stagger?: number;
  readonly weight?: 500 | 600 | 700;
  readonly colour?: string;
  readonly accent?: string;
  /** Arrive at once, with no blur: for lines that cut in on the beat. */
  readonly cut?: boolean;
  readonly style?: React.CSSProperties;
}> = ({
  text,
  at,
  out,
  size,
  stagger = 4,
  weight = 700,
  colour = C.ink,
  accent = C.accent,
  cut = false,
  style,
}) => {
  const frame = useCurrentFrame();
  const leave = out === undefined ? 0 : tween(frame, out, out + 8, 0, 1);
  let lit = false;
  const words = text.split(" ").map((raw) => {
    const marked = lit || raw.startsWith("*");
    lit = marked && !raw.endsWith("*");
    return { word: raw.split("*").join(""), marked };
  });

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "nowrap",
        whiteSpace: "nowrap",
        gap: size * 0.24,
        fontFamily: FONT,
        fontFeatureSettings: FEATURES,
        fontSize: size,
        fontWeight: weight,
        letterSpacing: "-0.035em",
        lineHeight: 1.08,
        color: colour,
        opacity: 1 - leave,
        filter: leave > 0 ? `blur(${leave * 18}px)` : undefined,
        ...style,
      }}
    >
      {words.map(({ word, marked }, index) => {
        const start = at + index * stagger;
        const arrive = cut
          ? Number(frame >= at)
          : tween(frame, start, start + 11, 0, 1, EASE);
        return (
          <span
            key={`${word}-${index}`}
            style={{
              display: "inline-block",
              color: marked ? accent : undefined,
              opacity: Math.min(arrive * 1.5, 1),
              translate: `0px ${(1 - arrive) * size * 0.32}px`,
              filter: arrive < 1 ? `blur(${(1 - arrive) * 16}px)` : undefined,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};
