import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ALERT, CLAMP, INK, Stage, headline, support } from "../theme";

// One template for every shouted label: they are meant to be edited as a set.
const CALLS = [
  { text: "BUY NOW", x: 1080, y: 150, size: 92, at: 0.1 },
  { text: "100x", x: 1500, y: 300, size: 120, at: 0.3 },
  { text: "SELL!", x: 1180, y: 430, size: 104, at: 0.5 },
  { text: "DIP?", x: 1560, y: 560, size: 88, at: 0.7 },
  { text: "MOON", x: 1120, y: 690, size: 112, at: 0.9 },
  { text: "ALL IN", x: 1460, y: 830, size: 84, at: 1.1 },
] as const;

/** Scene 2. Calls pile up, then each is struck through. */
export const Noise: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      {CALLS.map((call, index) => {
        const struck = (2 + index * 0.18) * fps;
        return (
          <div
            key={call.text}
            style={{
              position: "absolute",
              left: call.x,
              top: call.y,
              fontSize: call.size,
              fontWeight: 700,
              color: INK,
              opacity:
                interpolate(
                  frame,
                  [call.at * fps, call.at * fps + 5],
                  [0, 1],
                  CLAMP,
                ) * interpolate(frame, [struck, struck + 10], [1, 0.22], CLAMP),
              scale: interpolate(
                frame,
                [call.at * fps, call.at * fps + 8],
                [1.25, 1],
                { ...CLAMP, easing: Easing.bezier(0.16, 1, 0.3, 1) },
              ),
            }}
          >
            {call.text}
            <div
              style={{
                position: "absolute",
                left: -12,
                top: "52%",
                height: 8,
                borderRadius: 4,
                backgroundColor: ALERT,
                width: `${interpolate(frame, [struck, struck + 8], [0, 108], CLAMP)}%`,
              }}
            />
          </div>
        );
      })}
      <div style={{ position: "absolute", left: 140, top: 360, width: 860 }}>
        <h1
          style={{
            ...headline,
            opacity: interpolate(frame, [0.2 * fps, 0.9 * fps], [0, 1], CLAMP),
          }}
        >
          Everyone has a call.
        </h1>
        <p
          style={{
            ...support,
            opacity: interpolate(frame, [3.1 * fps, 3.8 * fps], [0, 1], CLAMP),
          }}
        >
          We tested them. None held up.
        </p>
      </div>
    </Stage>
  );
};
