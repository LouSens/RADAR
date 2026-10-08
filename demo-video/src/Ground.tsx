import { AbsoluteFill, interpolateColors, useCurrentFrame } from "remotion";
import { C, fade } from "./theme";
import { shot } from "./timing";

/**
 * The one coloured light, by frame of the whole film. Its colour follows the subject and
 * always glides from one to the next: there is no cut in this list.
 */
const LIGHT: readonly (readonly [number, string])[] = [
  [0, C.btc],
  [shot("meet").from, C.btc],
  [shot("meet").from + 26, C.accent],
  [shot("cards").from, C.accent],
  [shot("cards").from + 16, C.btc],
  [shot("cards").from + 36, C.gold],
  [shot("cards").from + 56, C.stock],
  [shot("cards").from + 76, C.stock],
  [shot("range").from + 10, C.btc],
  [shot("risk").from, C.btc],
  [shot("risk").from + 20, C.accent],
  [shot("refusals").from + 90, C.accent],
];

const hex = (colour: string): string => {
  const parts = colour.match(/[\d.]+/g) ?? ["0", "0", "0"];
  return `#${parts
    .slice(0, 3)
    .map((p) => Math.round(Number(p)).toString(16).padStart(2, "0"))
    .join("")}`;
};

/** The light's colour at a frame of the whole film, as hex. */
export const lightAt = (frame: number): string =>
  hex(
    interpolateColors(
      frame,
      LIGHT.map(([at]) => at),
      LIGHT.map(([, colour]) => colour),
    ),
  );

/**
 * The film's ground: the app's near-black, its glow at the top of the window in the
 * colour of what is being looked at, and its fine grid of points (index.css,
 * body::before and body::after), scaled up from a phone to this frame.
 */
export const Ground: React.FC = () => {
  const frame = useCurrentFrame();
  const light = lightAt(frame);
  // The light breathes a little, so a held frame is never dead.
  const breath = 1 + 0.04 * Math.sin(frame / 19);
  const points = "linear-gradient(to bottom, #000 0%, transparent 52%)";
  return (
    <AbsoluteFill style={{ backgroundColor: C.bg }}>
      <AbsoluteFill
        style={{
          background: [
            `radial-gradient(${110 * breath}% ${62 * breath}% at 50% -14%, ${fade(light, 0.3)}, transparent 62%)`,
            `radial-gradient(50% 42% at 100% 0%, ${fade(light, 0.13)}, transparent 70%)`,
            `radial-gradient(60% 46% at 50% 118%, ${fade(light, 0.1)}, transparent 70%)`,
          ].join(","),
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(rgba(255,255,255,0.075) 1.5px, transparent 1.5px) 0 0 / 44px 44px",
          maskImage: points,
          WebkitMaskImage: points,
        }}
      />
    </AbsoluteFill>
  );
};
