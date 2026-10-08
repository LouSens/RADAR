import { useFrame, useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { useEffect, useLayoutEffect, useRef } from "react";
import { useCurrentFrame } from "remotion";
import type { DataTexture, PerspectiveCamera, Scene } from "three";
import { HEIGHT, WIDTH } from "../timing";

type Vec = readonly [number, number, number];

/** Where the camera is and what it looks at. */
export interface View {
  readonly position: Vec;
  readonly target: Vec;
  readonly fov?: number;
  /** Tilt of the horizon, in radians. */
  readonly roll?: number;
}

/** The camera at a moment of the shot. The moment may fall between two frames. */
export type CameraAt = (frame: number) => View;
/** Moves named objects of the scene to where they are at a moment of the shot. */
export type MoveAt = (frame: number, scene: Scene) => void;

/** How many moments of a frame are drawn and averaged when it is blurred. */
const SAMPLES = 28;

/**
 * The light every object is seen in: a photographed studio for the metal and glass to
 * reflect, and one key light in the colour of the film's glow.
 */
const Studio: React.FC<{
  readonly room: DataTexture;
  readonly light: string;
  readonly turn: number;
  readonly strength: number;
}> = ({ room, light, turn, strength }) => {
  const { scene, advance } = useThree();

  useLayoutEffect(() => {
    scene.environment = room;
    scene.environmentIntensity = strength;
  }, [room, scene, strength]);

  useLayoutEffect(() => {
    scene.environmentRotation.set(0, turn, 0);
  }, [scene, turn]);

  useEffect(() => {
    // While rendering, the canvas draws only when told to. Draw once more with the
    // reflections in place, or a render tab's first frame has black metal.
    advance(performance.now());
  }, [advance, room]);

  return (
    <>
      <directionalLight position={[-3, 4, 5]} intensity={2.2} color={light} />
      <directionalLight position={[4, 1.5, -3]} intensity={1.4} color={light} />
      <directionalLight position={[0, 5, 2]} intensity={0.6} color="#ffffff" />
    </>
  );
};

/**
 * Draws the frame. With a shutter, the frame is drawn at several moments across the time
 * the shutter is open and the drawings are averaged, which is what a film camera does
 * with something moving fast. Each drawing is finished by the 3D canvas, so colours come
 * out exactly as they do unblurred, and is added to a plain canvas that is what is seen.
 */
const Draw: React.FC<{
  readonly camera: CameraAt;
  readonly move?: MoveAt;
  readonly shutter: number;
  readonly seen: React.RefObject<HTMLCanvasElement | null>;
}> = ({ camera, move, shutter, seen }) => {
  const frame = useCurrentFrame();

  useFrame((state) => {
    const paper = seen.current?.getContext("2d");
    if (!paper) {
      return;
    }
    const lens = state.camera as PerspectiveCamera;
    const count = shutter > 0 ? SAMPLES : 1;
    for (let i = 0; i < count; i++) {
      const moment =
        count === 1 ? frame : frame + ((i + 0.5) / count - 0.5) * shutter;
      const view = camera(moment);
      const roll = view.roll ?? 0;
      lens.position.set(view.position[0], view.position[1], view.position[2]);
      lens.up.set(Math.sin(roll), Math.cos(roll), 0);
      lens.lookAt(view.target[0], view.target[1], view.target[2]);
      lens.fov = view.fov ?? 28;
      lens.updateProjectionMatrix();
      move?.(moment, state.scene);
      state.gl.render(state.scene, lens);
      // A running average: what is there is scaled down to make room for this drawing,
      // then the drawing is added at its share. Adding each at 1/count instead would
      // round the dark parts of every drawing away.
      const share = 1 / (i + 1);
      if (i === 0) {
        paper.globalCompositeOperation = "copy";
        paper.globalAlpha = 1;
      } else {
        paper.globalCompositeOperation = "destination-out";
        paper.globalAlpha = share;
        paper.fillRect(0, 0, WIDTH, HEIGHT);
        paper.globalCompositeOperation = "lighter";
      }
      paper.drawImage(state.gl.domElement, 0, 0, WIDTH, HEIGHT);
    }
  }, 1);

  return null;
};

/** A 3D scene filling the frame, with nothing behind it: the film's ground shows through. */
export const Stage: React.FC<{
  readonly room: DataTexture;
  readonly light: string;
  readonly camera: CameraAt;
  readonly move?: MoveAt;
  /** How long the shutter is open this frame, in frames. Nothing is blurred at 0. */
  readonly shutter?: number;
  /** Turns the studio round the scene, to put a highlight where it is wanted. */
  readonly turn?: number;
  /** How bright the studio is in reflections. */
  readonly strength?: number;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({
  room,
  light,
  camera,
  move,
  shutter = 0,
  turn = 0,
  strength = 1,
  style,
  children,
}) => {
  const seen = useRef<HTMLCanvasElement | null>(null);
  return (
    <>
      <ThreeCanvas
        width={WIDTH}
        height={HEIGHT}
        style={{ position: "absolute", inset: 0, opacity: 0 }}
        camera={{ fov: 28, near: 0.02, far: 200, position: [0, 0, 10] }}
        gl={{ antialias: true, alpha: true }}
        dpr={1}
      >
        <Studio room={room} light={light} turn={turn} strength={strength} />
        <Draw camera={camera} move={move} shutter={shutter} seen={seen} />
        {children}
      </ThreeCanvas>
      <canvas
        ref={seen}
        width={WIDTH}
        height={HEIGHT}
        style={{ position: "absolute", inset: 0, ...style }}
      />
    </>
  );
};
