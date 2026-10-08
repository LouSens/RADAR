import { loadFont } from "@remotion/google-fonts/Inter";
import type React from "react";
import { AbsoluteFill } from "remotion";

const { fontFamily } = loadFont("normal", {
  weights: ["500", "700"],
  subsets: ["latin"],
});

export const FONT = fontFamily;
export const INK = "#eef0f6";
export const MUTED = "#8a8fa3";
export const ACCENT = "#1f9bb8";
export const CALM = "#2f9e6e";
export const ALERT = "#d9534f";
export const GOLD = "#c9952b";
export const BITCOIN = "#e8843c";
export const NIGHT = "#0b0e17";

/** Clamp on both sides: what nearly every keyframe here wants. */
export const CLAMP = {
  extrapolateLeft: "clamp",
  extrapolateRight: "clamp",
} as const;

/** The dark frame with one soft light from the top left, shared by every scene. */
export const Stage: React.FC<{ readonly children: React.ReactNode }> = ({
  children,
}) => (
  <AbsoluteFill
    style={{
      backgroundColor: NIGHT,
      backgroundImage:
        "radial-gradient(1200px 800px at 12% -10%, rgba(31,155,184,0.20), transparent 70%)",
      fontFamily: FONT,
      color: INK,
    }}
  >
    {children}
  </AbsoluteFill>
);

export const headline: React.CSSProperties = {
  fontSize: 116,
  fontWeight: 700,
  letterSpacing: "-0.03em",
  lineHeight: 1.05,
  margin: 0,
};

export const support: React.CSSProperties = {
  fontSize: 48,
  fontWeight: 500,
  color: MUTED,
  margin: 0,
  marginTop: 28,
};

/** The chart-line mark of the app, drawn up to `progress` (0 to 1). */
export const Mark: React.FC<{
  readonly size: number;
  readonly progress: number;
}> = ({ size, progress }) => (
  <svg width={size} height={size} viewBox="0 0 64 64">
    <rect width="64" height="64" rx="16" fill="#131827" />
    <path
      d="M12 44 L24 32 L33 39 L52 18"
      fill="none"
      stroke={ACCENT}
      strokeWidth="5"
      strokeLinecap="round"
      strokeLinejoin="round"
      pathLength={1}
      strokeDasharray={1}
      strokeDashoffset={1 - progress}
    />
    <circle
      cx="52"
      cy="18"
      r="4.5"
      fill={INK}
      opacity={progress > 0.95 ? 1 : 0}
    />
  </svg>
);
