import { useMemo } from "react";
import {
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  type Material,
  type Mesh,
  type Object3D,
  type Texture,
} from "three";

/** The model is in metres; the film's scenes are in tenths of a metre. */
export const PHONE_SCALE = 10;
/** The phone's size in the film's units (blender/build_assets.py). */
export const PHONE = { width: 0.715, height: 1.478, depth: 0.08 } as const;

/**
 * The phone, with the film's own materials in place of the ones named in Blender and a
 * page of the app lit on its screen.
 */
export const Phone: React.FC<{
  readonly object: Object3D;
  readonly screen: Texture;
  /** How bright the screen is, from 0 (off) to 1. */
  readonly lit?: number;
}> = ({ object, screen, lit = 1 }) => {
  const materials = useMemo<Record<string, Material>>(
    () => ({
      // Brushed, not polished: it shows the studio as broad soft bands.
      metal: new MeshStandardMaterial({
        color: "#9a9ea8",
        metalness: 1,
        roughness: 0.34,
      }),
      glass: new MeshPhysicalMaterial({
        color: "#06070a",
        roughness: 0.06,
        clearcoat: 1,
        clearcoatRoughness: 0.03,
        envMapIntensity: 1.1,
      }),
      back: new MeshPhysicalMaterial({
        color: "#1b1e26",
        metalness: 0.35,
        roughness: 0.42,
        clearcoat: 0.6,
        clearcoatRoughness: 0.25,
      }),
      screen: new MeshBasicMaterial({ map: screen, toneMapped: false }),
      // Clear glass over the screen: it only adds the room's reflection.
      sheen: new MeshPhysicalMaterial({
        color: "#000000",
        roughness: 0.04,
        transparent: true,
        opacity: 0.05,
        envMapIntensity: 1.6,
        depthWrite: false,
      }),
      lens: new MeshPhysicalMaterial({
        color: "#020203",
        roughness: 0.02,
        clearcoat: 1,
        envMapIntensity: 1.8,
      }),
      flash: new MeshStandardMaterial({ color: "#e9e4d2", roughness: 0.5 }),
    }),
    [screen],
  );

  useMemo(() => {
    object.traverse((child) => {
      const mesh = child as Mesh;
      if (!mesh.isMesh) {
        return;
      }
      const named = (mesh.material as Material).name;
      const mine = materials[named];
      if (mine) {
        mine.name = named;
        mesh.material = mine;
      }
    });
  }, [materials, object]);

  (materials.screen as MeshBasicMaterial).color.setScalar(lit);

  return <primitive object={object} scale={PHONE_SCALE} />;
};
