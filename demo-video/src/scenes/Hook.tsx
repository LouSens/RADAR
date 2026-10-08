import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ALERT, CLAMP, MUTED, Stage, headline, support } from "../theme";

// A calm line that falls away at the end: the move the film opens on.
const LINE =
  "M0 420 C160 400 240 440 400 410 S640 380 800 400 S1040 360 1180 380 L1300 392 L1420 640 L1560 700 L1920 720";

/** Scene 1. A price line draws across the frame and drops. */
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      <svg
        width={1920}
        height={1080}
        style={{
          position: "absolute",
          translate: interpolate(
            frame,
            [1.9 * fps, 2.4 * fps],
            ["0px 0px", "0px 26px"],
            { ...CLAMP, easing: Easing.bezier(0.3, 0, 0.2, 1) },
          ),
        }}
      >
        <path
          d={LINE}
          fill="none"
          stroke={frame > 2.1 * fps ? ALERT : MUTED}
          strokeWidth={6}
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={interpolate(frame, [0, 2.6 * fps], [1, 0], {
            ...CLAMP,
            easing: Easing.bezier(0.5, 0, 0.3, 1),
          })}
        />
      </svg>
      <div style={{ position: "absolute", left: 140, top: 130 }}>
        <h1
          style={{
            ...headline,
            opacity: interpolate(frame, [0.3 * fps, 1 * fps], [0, 1], CLAMP),
            translate: interpolate(
              frame,
              [0.3 * fps, 1 * fps],
              ["0px 24px", "0px 0px"],
              { ...CLAMP, easing: Easing.bezier(0.16, 1, 0.3, 1) },
            ),
          }}
        >
          Your portfolio just moved.
        </h1>
        <p
          style={{
            ...support,
            opacity: interpolate(frame, [2.6 * fps, 3.3 * fps], [0, 1], CLAMP),
          }}
        >
          Do you know why?
        </p>
      </div>
    </Stage>
  );
};
