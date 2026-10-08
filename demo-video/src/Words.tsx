import { loadFont } from "@remotion/google-fonts/Inter";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const { fontFamily } = loadFont("normal", {
  weights: ["500", "600"],
  subsets: ["latin"],
});

export const INK = "#0b1220";
export const CYAN = "#1aa7c9";

/**
 * A line of type that arrives a word at a time, each word settling out of a blur, and
 * leaves by rushing towards the viewer. Words wrapped in asterisks take the brand colour.
 */
export const Words: React.FC<{
  readonly text: string;
  readonly from: number;
  readonly to: number;
  readonly size: number;
  readonly top: number;
  readonly stagger?: number;
  readonly weight?: 500 | 600;
  readonly colour?: string;
}> = ({
  text,
  from,
  to,
  size,
  top,
  stagger = 5,
  weight = 600,
  colour = INK,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const leave = interpolate(frame, [to - 9, to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (frame < from || frame > to) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top,
        display: "flex",
        justifyContent: "center",
        gap: size * 0.26,
        fontFamily,
        fontSize: size,
        fontWeight: weight,
        letterSpacing: "-0.035em",
        lineHeight: 1,
        color: colour,
        opacity: 1 - leave,
        scale: 1 + leave * 0.5,
        filter: `blur(${leave * 26}px)`,
      }}
    >
      {text.split(" ").map((word, index) => {
        const arrive = spring({
          frame: frame - from - index * stagger,
          fps,
          config: { damping: 18, mass: 0.6 },
        });
        const accent = word.startsWith("*");
        return (
          <span
            key={`${word}-${index}`}
            style={{
              display: "inline-block",
              color: accent ? CYAN : undefined,
              opacity: Math.min(arrive * 1.6, 1),
              translate: `0px ${(1 - arrive) * size * 0.45}px`,
              filter: `blur(${(1 - Math.min(arrive, 1)) * 14}px)`,
            }}
          >
            {word.split("*").join("")}
          </span>
        );
      })}
    </div>
  );
};
