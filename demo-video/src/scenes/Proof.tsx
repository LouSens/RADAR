import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ACCENT, CLAMP, MUTED, Stage, headline } from "../theme";

// Published results of the project's own tests (README, "What the research found").
const RESULTS = [
  {
    top: 6,
    of: "of 6",
    caption: "forecasts of how much it moves, best of every method tried",
  },
  {
    top: 35,
    of: "of 36",
    caption: "loss limits that held as often as they said",
  },
  {
    top: 61,
    of: "%",
    caption:
      "right on news tone, against 52% before training, on 700 unseen headlines",
  },
] as const;

/** Scene 7. Three results count up and lock. */
export const Proof: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 130 }}>
        <h1
          style={{
            ...headline,
            opacity: interpolate(frame, [0, 0.6 * fps], [0, 1], CLAMP),
          }}
        >
          Tested before trusted.
        </h1>
        <div style={{ display: "flex", gap: 70, marginTop: 110 }}>
          {RESULTS.map((result, index) => {
            const start = (0.7 + index * 0.6) * fps;
            return (
              <div
                key={result.caption}
                style={{
                  width: 500,
                  opacity: interpolate(
                    frame,
                    [start, start + 10],
                    [0, 1],
                    CLAMP,
                  ),
                }}
              >
                <div
                  style={{
                    fontSize: 190,
                    fontWeight: 700,
                    color: ACCENT,
                    lineHeight: 1,
                    whiteSpace: "nowrap",
                  }}
                >
                  {Math.round(
                    interpolate(
                      frame,
                      [start, start + 0.9 * fps],
                      [0, result.top],
                      {
                        ...CLAMP,
                        easing: Easing.bezier(0.16, 1, 0.3, 1),
                      },
                    ),
                  )}
                  <span style={{ fontSize: 60, color: MUTED, marginLeft: 14 }}>
                    {result.of}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 38,
                    color: MUTED,
                    marginTop: 26,
                    lineHeight: 1.3,
                    opacity: interpolate(
                      frame,
                      [start + 0.8 * fps, start + 1.3 * fps],
                      [0, 1],
                      CLAMP,
                    ),
                  }}
                >
                  {result.caption}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </Stage>
  );
};
