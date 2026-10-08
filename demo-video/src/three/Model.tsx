import { useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";
import type { Mesh, Object3D } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

export type Objects = Readonly<Record<string, Object3D>>;

/**
 * The objects made in Blender (public/assets/<name>.glb), all loaded before anything is
 * drawn. Call this outside the 3D canvas: a hold placed inside it comes too late, and
 * the first frames render empty.
 */
export const useObjects = (names: readonly string[]): Objects | null => {
  const [objects, setObjects] = useState<Objects | null>(null);
  const [handle] = useState(() => delayRender("Loading the 3D objects"));
  const key = names.join(",");

  useEffect(() => {
    const loader = new GLTFLoader();
    Promise.all(
      key.split(",").map(async (name) => {
        const file = await loader.loadAsync(staticFile(`assets/${name}.glb`));
        file.scene.traverse((child) => {
          if ((child as Mesh).isMesh) {
            child.castShadow = true;
          }
        });
        return [name, file.scene] as const;
      }),
    )
      .then((loaded) => {
        setObjects(Object.fromEntries(loaded));
        continueRender(handle);
      })
      .catch((error) => cancelRender(error));
  }, [handle, key]);

  return objects;
};

export const Model: React.FC<{
  readonly object: Object3D;
  readonly position: readonly [number, number, number];
  readonly rotation?: readonly [number, number, number];
  readonly scale?: number;
}> = ({ object, position, rotation = [0, 0, 0], scale = 1 }) => (
  <group
    position={[position[0], position[1], position[2]]}
    rotation={[rotation[0], rotation[1], rotation[2]]}
    scale={scale}
  >
    <primitive object={object} />
  </group>
);
