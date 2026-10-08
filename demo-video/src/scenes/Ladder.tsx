import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ACCENT, CLAMP, INK, MUTED, Stage, headline, support } from "../theme";

// An invented purchase, split into three prices going down.
const RUNGS = [
  { label: "Now", price: "$4,110", amount: "$40", x: 1560, y: 330 },
  { label: "or lower", price: "$4,020", amount: "$40", x: 1330, y: 520 },
  { label: "or lower", price: "$3,930", amount: "$40", x: 1100, y: 710 },
] as const;

/** Scene 5. The plan becomes a short list of purchases at stepped prices. */
export const Ladder: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      <div style={{ position: "absolute", left: 140, top: 150, width: 860 }}>
        <h1
          style={{
            ...headline,
            fontSize: 104,
            opacity: interpolate(frame, [0, 0.7 * fps], [0, 1], CLAMP),
          }}
        >
          It turns your plan into a list.
        </h1>
        <p
          style={{
            ...support,
            opacity: interpolate(frame, [2.8 * fps, 3.5 * fps], [0, 1], CLAMP),
          }}
        >
          What to put in, and at what price.
        </p>
      </div>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <path
          d="M1700 300 L1470 490 L1240 680 L1010 870"
          fill="none"
          stroke="rgba(255,255,255,0.18)"
          strokeWidth={5}
          strokeDasharray="4 18"
          strokeLinecap="round"
        />
      </svg>
      {RUNGS.map((rung, index) => {
        const start = (0.9 + index * 0.7) * fps;
        return (
          <div
            key={rung.price}
            style={{
              position: "absolute",
              left: rung.x - 250,
              top: rung.y,
              width: 380,
              padding: "30px 36px",
              borderRadius: 30,
              backgroundColor: "rgba(255,255,255,0.06)",
              border: `2px solid ${index === 0 ? ACCENT : "rgba(255,255,255,0.10)"}`,
              opacity: interpolate(frame, [start, start + 10], [0, 1], CLAMP),
              translate: interpolate(
                frame,
                [start, start + 0.6 * fps],
                ["90px -40px", "0px 0px"],
                {
                  ...CLAMP,
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                },
              ),
            }}
          >
            <div style={{ fontSize: 30, color: MUTED }}>{rung.label}</div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginTop: 6,
              }}
            >
              <span style={{ fontSize: 62, fontWeight: 700, color: INK }}>
                {rung.price}
              </span>
              <span style={{ fontSize: 40, color: ACCENT }}>{rung.amount}</span>
            </div>
          </div>
        );
      })}
    </Stage>
  );
};
