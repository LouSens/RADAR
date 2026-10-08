import { AbsoluteFill, useCurrentFrame } from "remotion";
import { HEIGHT, WIDTH } from "./timing";

/**
 * A faint film grain over the whole frame, different on every frame, so that the dark
 * ground and the glass are never perfectly clean. It is noise from the frame's own
 * number: the same frame always gets the same grain.
 */
export const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ mixBlendMode: "overlay", opacity: 0.11 }}>
      <svg width={WIDTH} height={HEIGHT}>
        <filter id="grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.9"
            numOctaves="2"
            seed={frame}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width={WIDTH} height={HEIGHT} filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};
