import { AbsoluteFill, useCurrentFrame } from "remotion";
import { HANDOVER, SCREEN } from "../DeskLayer";
import { C } from "../theme";
import { PHONE, Phone } from "../three/Phone";
import { Stage, type View } from "../three/Stage";
import { useLoaded } from "../three/assets";
import { EASE, HEIGHT, WIDTH, shot, tween } from "../timing";

const both = shot("both").from;

/** The lens: straight on, so that the phone's screen is a true rectangle in the frame. */
const FOV = 28;
/** The lit screen is the phone less its bezel (blender/build_assets.py). */
const LIT = { w: PHONE.width - 0.06, h: PHONE.height - 0.06 } as const;
/** How far away the phone is, for its screen to be as tall as its place in the frame. */
const PER_UNIT = SCREEN.h / LIT.h;
const FAR = HEIGHT / 2 / Math.tan((FOV * Math.PI) / 360) / PER_UNIT;
const AT = {
  x: (SCREEN.x + SCREEN.w / 2 - WIDTH / 2) / PER_UNIT,
  y: -(SCREEN.y + SCREEN.h / 2 - HEIGHT / 2) / PER_UNIT,
} as const;

const camera = (): View => ({
  position: [0, 0, FAR],
  target: [0, 0, 0],
  fov: FOV,
});

/** The phone comes up into the frame first, before anything of Home moves. */
export const SLIDES = [0, 12] as const;

/**
 * Shot 9. The phone comes up on the right; Home's pieces go across behind it and arrive
 * on its screen (DeskLayer, DeskOnPhone); then its own screen takes over, and it stands
 * clear and still until the radar's line.
 */
export const Both: React.FC = () => {
  const frame = useCurrentFrame();
  const assets = useLoaded();
  if (!assets) {
    return null;
  }
  const up = tween(frame, SLIDES[0], SLIDES[1], 0, 1, EASE);
  const lit = tween(both + frame, HANDOVER[0], HANDOVER[1], 0, 1, (t) => t);
  return (
    <AbsoluteFill>
      <Stage room={assets.room} light={C.accent} camera={camera} turn={0.5}>
        <group position={[AT.x, AT.y - (1 - up) * 2.6, 0]}>
          <Phone object={assets.phone} screen={assets.screens.home} lit={lit} />
        </group>
      </Stage>
    </AbsoluteFill>
  );
};
