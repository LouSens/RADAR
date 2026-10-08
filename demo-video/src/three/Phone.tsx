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
 * Brushed titanium. The grain runs along the frame's length, so across the band it is a
 * stack of fine lines: they are made from the height across the band alone, with a slow
 * drift along it. Each line roughens the surface a little and leans its normal a little,
 * which pulls a highlight out into a streak the way brushing does. The grain fades out
 * where a line would be finer than a pixel, so the far phone does not shimmer.
 */
const titanium = (): MeshStandardMaterial => {
  const material = new MeshStandardMaterial({
    color: "#6d6f76",
    metalness: 1,
    roughness: 0.36,
  });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec3 vAt;\nvarying vec3 vAcross;",
      )
      .replace(
        "#include <begin_vertex>",
        "#include <begin_vertex>\nvAt = position;\nvAcross = normalize(normalMatrix * vec3(0.0, 0.0, 1.0));",
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
         varying vec3 vAt;
         varying vec3 vAcross;
         float grainHash(float x) { return fract(sin(x * 127.1) * 43758.5453); }
         float grainLine(float x) {
           float i = floor(x);
           float f = fract(x);
           return mix(grainHash(i), grainHash(i + 1.0), f * f * (3.0 - 2.0 * f));
         }
         float grainAt(vec3 p) {
           float along = (p.x + p.y) * 14.0;
           float across = p.z;
           float coarse = grainLine(across * 9000.0 + grainLine(along) * 3.0);
           float fine = grainLine(across * 31000.0 + grainLine(along * 3.1 + 7.0) * 5.0);
           return coarse * 0.6 + fine * 0.4 - 0.5;
         }`,
      )
      .replace(
        "#include <roughnessmap_fragment>",
        `#include <roughnessmap_fragment>
         float grainSeen = 1.0 - smoothstep(0.25, 0.9, fwidth(vAt.z * 9000.0));
         float grain = grainAt(vAt) * grainSeen;
         roughnessFactor = clamp(roughnessFactor + grain * 0.22, 0.05, 1.0);`,
      )
      .replace(
        "#include <normal_fragment_maps>",
        `#include <normal_fragment_maps>
         normal = normalize(normal + vAcross * grain * 0.1);`,
      );
  };
  return material;
};

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
      metal: titanium(),
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
