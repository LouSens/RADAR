import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, FEATURES, FONT, fade } from "../theme";
import { Mark } from "../three/Mark";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { BEAT, COPY, tween } from "../timing";
import { Words } from "../Words";

/** The cut from the three lines to the mark: on a beat, with the third line read. */
const MARK = 52;

const cameraAt = (frame: number): View => ({
  // A slow move in, so the last picture is never still.
  position: [0, 0, 13.4 - tween(frame, MARK, 90, 0, 0.9, (t) => t)],
  target: [0, 0, 0],
});

/**
 * Shot 8. What RADAR will not do, a line a beat, each cutting in under the last; then a
 * cut to the mark and what it does do.
 */
export const Refusals: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const said = Math.min(Math.floor(frame / BEAT), COPY.refusals.length - 1);
  const settle = spring({
    frame: frame - MARK,
    fps,
    config: { damping: 16, mass: 0.5, stiffness: 160 },
  });

  // The mark's scene is there from the start and only uncovered at the cut, so the cut
  // costs nothing.
  const cut = frame >= MARK;

  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          opacity: cut ? 0 : 1,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {COPY.refusals.map((line, i) => (
            <div
              key={line}
              style={{
                fontFamily: FONT,
                fontFeatureSettings: FEATURES,
                fontSize: 148,
                fontWeight: 700,
                letterSpacing: "-0.04em",
                lineHeight: 1.08,
                whiteSpace: "nowrap",
                // The line just said is bright; the ones before it stand back.
                color: i === said ? C.ink : C.faint,
                visibility: i <= said ? "visible" : "hidden",
              }}
            >
              {line}
            </div>
          ))}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: cut ? 1 : 0 }}>
        <Stage
          room={assets.room}
          light={C.accent}
          camera={cameraAt}
          style={{ filter: `drop-shadow(0 0 22px ${fade(C.accent, 0.42)})` }}
        >
          <group position={[0, 1.42, 0]} scale={0.94 + 0.06 * settle}>
            <Mark ring={1} line={1} dot={1} />
          </group>
        </Stage>
        <AbsoluteFill style={{ alignItems: "center", top: 560 }}>
          <Words text={`*${COPY.signoff[0]}*`} at={MARK} size={150} cut />
        </AbsoluteFill>
        <AbsoluteFill style={{ alignItems: "center", top: 768 }}>
          <Words
            text={COPY.signoff[1]}
            at={MARK + 5}
            size={76}
            weight={600}
            stagger={4}
          />
        </AbsoluteFill>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
