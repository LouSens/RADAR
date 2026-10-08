import { loadFont } from "@remotion/google-fonts/Inter";
import { interpolate, useCurrentFrame } from "remotion";

const { fontFamily } = loadFont("normal", {
  weights: ["500"],
  subsets: ["latin"],
});

const FADE = 8;

/**
 * One line of copy over a plate. Small, lower left, inside the safe area: it supports
 * the picture and never competes with it. It only fades; nothing slides or scales.
 */
export const Super: React.FC<{
  readonly text: string;
  readonly from: number;
  readonly to: number;
}> = ({ text, from, to }) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        bottom: 104,
        fontFamily,
        fontSize: 44,
        fontWeight: 500,
        letterSpacing: "-0.01em",
        color: "rgba(244, 242, 236, 0.94)",
        textShadow: "0 1px 14px rgba(0, 0, 0, 0.45)",
        opacity: interpolate(
          frame,
          [from, from + FADE, to - FADE, to],
          [0, 1, 1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        ),
      }}
    >
      {text}
    </div>
  );
};
