import {
  Easing,
  interpolate,
  random,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ACCENT, ALERT, CLAMP, INK, Stage, headline, support } from "../theme";

const START = { x: 240, y: 640 };
const WIDTH = 1500;
const STEPS = 40;

/** One made-up path from today outwards: seeded, so every render draws the same. */
const path = (seed: number): string => {
  let y = START.y;
  let d = `M${START.x} ${y}`;
  for (let step = 1; step <= STEPS; step++) {
    y += (random(`path-${seed}-${step}`) - 0.5) * 34 * (1 + step / 26);
    d += ` L${START.x + (WIDTH * step) / STEPS} ${y.toFixed(1)}`;
  }
  return d;
};
const PATHS = Array.from({ length: 46 }, (_, seed) => path(seed));

/** Scene 6. A fan of possible futures, and the band most of them stay inside. */
export const Futures: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <path
          d={`M${START.x} ${START.y} L${START.x + WIDTH} 400 L${START.x + WIDTH} 900 Z`}
          fill={ACCENT}
          opacity={interpolate(frame, [2.6 * fps, 3.4 * fps], [0, 0.13], CLAMP)}
        />
        {PATHS.map((d, index) => (
          <path
            key={d}
            d={d}
            fill="none"
            stroke={ACCENT}
            strokeWidth={2.5}
            opacity={0.5}
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={interpolate(
              frame,
              [0.4 * fps + index * 1.2, 2.4 * fps + index * 1.2],
              [1, 0],
              { ...CLAMP, easing: Easing.bezier(0.3, 0, 0.2, 1) },
            )}
          />
        ))}
        <circle cx={START.x} cy={START.y} r={13} fill={INK} />
        <line
          x1={START.x + WIDTH}
          x2={START.x + WIDTH + 70}
          y1={900}
          y2={900}
          stroke={ALERT}
          strokeWidth={6}
          strokeLinecap="round"
          opacity={interpolate(frame, [3.6 * fps, 4.1 * fps], [0, 1], CLAMP)}
        />
      </svg>
      <div style={{ position: "absolute", left: 140, top: 120 }}>
        <h1
          style={{
            ...headline,
            opacity: interpolate(frame, [0, 0.7 * fps], [0, 1], CLAMP),
          }}
        >
          10,000 possible futures.
        </h1>
        <p
          style={{
            ...support,
            opacity: interpolate(frame, [3.4 * fps, 4.1 * fps], [0, 1], CLAMP),
          }}
        >
          So you know how bad a bad day can be.
        </p>
      </div>
    </Stage>
  );
};
