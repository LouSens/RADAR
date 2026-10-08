import { useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { useEffect, useLayoutEffect } from "react";
import type { DataTexture, PerspectiveCamera } from "three";
import { HEIGHT, WIDTH } from "../timing";

type Vec = readonly [number, number, number];

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
      <directionalLight position={[-3, 4, 5]} intensity={2.6} color={light} />
      <directionalLight position={[4, 1.5, -3]} intensity={1.4} color={light} />
      <directionalLight position={[0, 5, 2]} intensity={0.7} color="#ffffff" />
    </>
  );
};

/**
 * Where the camera is this frame. Set in a layout effect, which runs before the canvas
 * is told to draw the frame.
 */
export const Rig: React.FC<{
  readonly position: Vec;
  readonly target: Vec;
  readonly fov?: number;
  readonly roll?: number;
}> = ({ position, target, fov = 28, roll = 0 }) => {
  const camera = useThree((state) => state.camera) as PerspectiveCamera;
  useLayoutEffect(() => {
    camera.position.set(position[0], position[1], position[2]);
    camera.up.set(Math.sin(roll), Math.cos(roll), 0);
    camera.lookAt(target[0], target[1], target[2]);
    camera.fov = fov;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  });
  return null;
};

/** A 3D scene filling the frame, with nothing behind it: the film's ground shows through. */
export const Stage: React.FC<{
  readonly room: DataTexture;
  readonly light: string;
  /** Turns the studio round the scene, to put a highlight where it is wanted. */
  readonly turn?: number;
  /** How bright the studio is in reflections. */
  readonly strength?: number;
  readonly style?: React.CSSProperties;
  readonly children: React.ReactNode;
}> = ({ room, light, turn = 0, strength = 1, style, children }) => (
  <ThreeCanvas
    width={WIDTH}
    height={HEIGHT}
    style={{ position: "absolute", inset: 0, ...style }}
    camera={{ fov: 28, near: 0.02, far: 200, position: [0, 0, 10] }}
    gl={{ antialias: true, alpha: true }}
    dpr={1}
  >
    <Studio room={room} light={light} turn={turn} strength={strength} />
    {children}
  </ThreeCanvas>
);
