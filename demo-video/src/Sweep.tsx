import { AbsoluteFill } from "remotion";
import { C, fade } from "./theme";
import { EASE_IN_OUT, HEIGHT, SWEEP, WIDTH, tween } from "./timing";

/** Where the radar line turns from. */
const CX = WIDTH / 2;
const CY = HEIGHT / 2;
/** Far enough to reach every corner. */
const REACH = Math.hypot(CX, CY) + 40;

/** How far round the line is, in degrees from twelve o'clock, `since` frames in. */
export const sweepAngle = (since: number): number =>
  tween(since, 0, SWEEP, 0, 360, EASE_IN_OUT);

/**
 * One side of a change of scene. The line turns once round the centre; the scene coming
 * in shows only where the line has passed, and the scene going out only where it has not.
 */
export const Swept: React.FC<{
  readonly since: number;
  readonly side: "in" | "out";
  readonly children: React.ReactNode;
}> = ({ since, side, children }) => {
  const angle = sweepAngle(since);
  const soft = Math.min(angle, 5);
  let mask: string | undefined;
  if (since < 0) {
    mask =
      side === "in" ? "linear-gradient(transparent, transparent)" : undefined;
  } else if (since >= SWEEP) {
    mask =
      side === "in" ? undefined : "linear-gradient(transparent, transparent)";
  } else if (side === "in") {
    mask = `conic-gradient(from 0deg at ${CX}px ${CY}px, #000 ${angle - soft}deg, transparent ${angle}deg)`;
  } else {
    mask = `conic-gradient(from 0deg at ${CX}px ${CY}px, transparent ${angle - soft}deg, #000 ${angle}deg)`;
  }
  return (
    <AbsoluteFill style={{ maskImage: mask, WebkitMaskImage: mask }}>
      {children}
    </AbsoluteFill>
  );
};

/** The line itself, with its fading trail and the faint rings of a radar's face. */
export const SweepLine: React.FC<{ readonly since: number }> = ({ since }) => {
  if (since < -4 || since > SWEEP + 6) {
    return null;
  }
  const angle = sweepAngle(since);
  const presence =
    tween(since, -4, 2, 0, 1) * (1 - tween(since, SWEEP - 3, SWEEP + 6, 0, 1));
  const trail = 80;
  return (
    <AbsoluteFill style={{ opacity: presence }}>
      {[0.24, 0.5, 0.78].map((r) => (
        <div
          key={r}
          style={{
            position: "absolute",
            left: CX - REACH * r,
            top: CY - REACH * r,
            width: REACH * r * 2,
            height: REACH * r * 2,
            borderRadius: "50%",
            border: `1.5px solid ${fade(C.accent, 0.13)}`,
          }}
        />
      ))}
      <AbsoluteFill
        style={{
          background: `conic-gradient(from ${angle - trail}deg at ${CX}px ${CY}px, transparent 0deg, ${fade(C.accent, 0.03)} ${trail * 0.4}deg, ${fade(C.accent, 0.3)} ${trail}deg, transparent ${trail}deg)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: CX - 2,
          top: CY - REACH,
          width: 4,
          height: REACH,
          transformOrigin: "50% 100%",
          rotate: `${angle}deg`,
          borderRadius: 2,
          background: `linear-gradient(to top, ${C.accent}, ${fade(C.accent, 0.75)})`,
          boxShadow: `0 0 18px 3px ${fade(C.accent, 0.65)}, 0 0 60px 10px ${fade(C.accent, 0.3)}`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: CX - 9,
          top: CY - 9,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: C.accent,
          boxShadow: `0 0 30px 8px ${fade(C.accent, 0.6)}`,
        }}
      />
    </AbsoluteFill>
  );
};
