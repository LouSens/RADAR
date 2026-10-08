import { AbsoluteFill } from "remotion";
import { BEAT } from "../timing";
import { Words } from "../Words";

/**
 * A shot that is not built yet: its words only, a line a beat, so the film's length and
 * rhythm can be read before its pictures exist.
 */
export const Empty: React.FC<{
  readonly lines: readonly string[];
  readonly step?: number;
}> = ({ lines, step = BEAT * 2 }) => (
  <AbsoluteFill
    style={{
      alignItems: "center",
      justifyContent: "center",
      flexDirection: "column",
      gap: 26,
    }}
  >
    {lines.map((line, i) => (
      <Words key={line + i} text={line} at={6 + i * step} size={104} />
    ))}
  </AbsoluteFill>
);
