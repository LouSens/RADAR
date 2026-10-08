import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import {
  ACCENT,
  BITCOIN,
  CLAMP,
  GOLD,
  INK,
  MUTED,
  Stage,
  headline,
  support,
} from "../theme";

// An invented account: what is held now, and the share the plan asks for.
const HOLDINGS = [
  { name: "US stocks", now: 13, plan: 25, colour: ACCENT },
  { name: "Gold", now: 6, plan: 15, colour: GOLD },
  { name: "Bitcoin", now: 8, plan: 9, colour: BITCOIN },
  { name: "Cash", now: 73, plan: 51, colour: MUTED },
] as const;
const TOTAL = 12480;

/** Scene 4. The account is read, and set against the plan. */
export const Account: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.round(
    interpolate(frame, [0.6 * fps, 2 * fps], [0, TOTAL], {
      ...CLAMP,
      easing: Easing.bezier(0.16, 1, 0.3, 1),
    }),
  );

  return (
    <Stage>
      <div style={{ position: "absolute", left: 140, top: 150, width: 800 }}>
        <h1
          style={{
            ...headline,
            fontSize: 104,
            opacity: interpolate(frame, [0, 0.7 * fps], [0, 1], CLAMP),
          }}
        >
          It reads your account.
        </h1>
        <p
          style={{
            ...support,
            opacity: interpolate(frame, [2.4 * fps, 3.1 * fps], [0, 1], CLAMP),
          }}
        >
          Read-only. Every few minutes. Nothing to type.
        </p>
      </div>
      <div
        style={{
          position: "absolute",
          left: 1020,
          top: 150,
          width: 760,
          padding: 56,
          borderRadius: 40,
          backgroundColor: "rgba(255,255,255,0.05)",
          border: "2px solid rgba(255,255,255,0.09)",
          opacity: interpolate(frame, [0.3 * fps, 0.9 * fps], [0, 1], CLAMP),
          translate: interpolate(
            frame,
            [0.3 * fps, 1 * fps],
            ["0px 40px", "0px 0px"],
            {
              ...CLAMP,
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            },
          ),
        }}
      >
        <div style={{ fontSize: 34, color: MUTED }}>Your account</div>
        <div
          style={{
            fontSize: 124,
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          ${total.toLocaleString("en-US")}
        </div>
        {HOLDINGS.map((holding, index) => {
          const start = (1.4 + index * 0.25) * fps;
          return (
            <div key={holding.name} style={{ marginTop: 40 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 36,
                }}
              >
                <span>{holding.name}</span>
                <span style={{ color: MUTED }}>
                  {holding.now}% · plan {holding.plan}%
                </span>
              </div>
              <div
                style={{
                  position: "relative",
                  height: 18,
                  marginTop: 14,
                  borderRadius: 9,
                  backgroundColor: "rgba(255,255,255,0.08)",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    borderRadius: 9,
                    backgroundColor: holding.colour,
                    width: `${interpolate(
                      frame,
                      [start, start + 0.8 * fps],
                      [0, holding.now],
                      {
                        ...CLAMP,
                        easing: Easing.bezier(0.16, 1, 0.3, 1),
                      },
                    )}%`,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: -8,
                    width: 5,
                    height: 34,
                    borderRadius: 3,
                    backgroundColor: INK,
                    left: `${holding.plan}%`,
                    opacity: interpolate(
                      frame,
                      [3.2 * fps, 3.7 * fps],
                      [0, 1],
                      CLAMP,
                    ),
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Stage>
  );
};
