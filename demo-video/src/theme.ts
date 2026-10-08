import { loadFont } from "@remotion/google-fonts/Inter";

const inter = loadFont("normal", {
  weights: ["400", "500", "600", "700"],
  subsets: ["latin"],
});

/** Inter, as in the app, with the same alternate figures switched on. */
export const FONT = inter.fontFamily;
export const FEATURES = '"cv02", "cv03", "cv04", "cv11"';
export const NUM_FEATURES = '"tnum", "cv11", "ss01"';

/** The app's colours, copied from frontend/src/index.css. Keep the two in step. */
export const C = {
  bg: "#090a0e",
  ink: "#f3f4f7",
  muted: "#9ea2b0",
  faint: "#7c8095",
  line: "rgba(255, 255, 255, 0.085)",
  lineStrong: "rgba(255, 255, 255, 0.18)",
  accent: "#62cfe8",
  calm: "#64d599",
  alert: "#f46f68",
  btc: "#eea65b",
  gold: "#e1c981",
  stock: "#97a0ef",
} as const;

export type Tone = "accent" | "btc" | "gold" | "stock";

/** A colour with some of its strength taken out, as `color-mix(... transparent)` does. */
export const fade = (hex: string, alpha: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};
