import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ACCENT, CLAMP, Mark, Stage, support } from "../theme";

/** Scenes 3 and 8. One radar sweep, then the mark, the name and a line under it. */
export const Reveal: React.FC<{
  readonly line: string;
  readonly address?: string;
}> = ({ line, address }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <Stage>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div
          style={{
            position: "absolute",
            width: 1500,
            height: 1500,
            borderRadius: "50%",
            background: `conic-gradient(from 0deg, transparent 0deg, ${ACCENT}55 50deg, transparent 52deg)`,
            opacity: interpolate(
              frame,
              [0, 0.4 * fps, 1.6 * fps, 2.2 * fps],
              [0, 1, 1, 0],
              CLAMP,
            ),
            rotate: interpolate(frame, [0, 2.2 * fps], ["-90deg", "270deg"], {
              ...CLAMP,
              easing: Easing.bezier(0.4, 0, 0.2, 1),
            }),
          }}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 44,
            scale: interpolate(frame, [0.5 * fps, 1.5 * fps], [0.92, 1], {
              ...CLAMP,
              easing: Easing.bezier(0.16, 1, 0.3, 1),
              output: "perceptual-scale",
            }),
            opacity: interpolate(frame, [0.5 * fps, 1.1 * fps], [0, 1], CLAMP),
          }}
        >
          <Mark
            size={190}
            progress={interpolate(frame, [0.7 * fps, 1.7 * fps], [0, 1], {
              ...CLAMP,
              easing: Easing.bezier(0.5, 0, 0.2, 1),
            })}
          />
          <div
            style={{ fontSize: 200, fontWeight: 700, letterSpacing: "0.02em" }}
          >
            RADAR
          </div>
        </div>
        <p
          style={{
            ...support,
            fontSize: 56,
            marginTop: 56,
            opacity: interpolate(frame, [1.7 * fps, 2.4 * fps], [0, 1], CLAMP),
          }}
        >
          {line}
        </p>
        {address ? (
          <p
            style={{
              ...support,
              color: ACCENT,
              opacity: interpolate(
                frame,
                [2.6 * fps, 3.2 * fps],
                [0, 1],
                CLAMP,
              ),
            }}
          >
            {address}
          </p>
        ) : null}
      </AbsoluteFill>
    </Stage>
  );
};
