import { loadFont } from "@remotion/google-fonts/Inter";

const inter = loadFont("normal", {
  weights: ["400", "500", "600", "700"],
  subsets: ["latin"],
});

/** Inter, as in the app, with the same alternate figures switched on. */
export const FONT = inter.fontFamily;
export const FEATURES = '"cv02", "cv03", "cv04", "cv11"';
export const NUM_FEATURES = '"tnum", "cv11", "ss01"';

/**
 * The app's colours, copied from frontend/src/index.css. Keep the two in step. The three
 * markets are metals: copper, gold and steel.
 */
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
  btc: "#ce8e64",
  gold: "#d7bb65",
  stock: "#a6b5ca",
} as const;

export type Tone = "accent" | "btc" | "gold" | "stock";

/** A colour with some of its strength taken out, as `color-mix(... transparent)` does. */
export const fade = (hex: string, alpha: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

const blend = (hex: string, towards: number, share: number): string => {
  const n = parseInt(hex.slice(1), 16);
  const mix = (channel: number): number =>
    Math.round(channel * (1 - share) + towards * share);
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
};

/** A metal's tone where the light falls on it, and where it does not (viz.tsx). */
export const lighter = (hex: string): string => blend(hex, 255, 0.17);
export const darker = (hex: string): string => blend(hex, 0, 0.08);

/**
 * A holding's colour laid on as brushed metal: lighter along the top and darker along the
 * foot, as the app's bars are (viz.tsx, `metal`).
 */
export const metal = (hex: string): string =>
  `linear-gradient(180deg, ${lighter(hex)} 0%, ${hex} 45%, ${darker(hex)} 100%)`;
