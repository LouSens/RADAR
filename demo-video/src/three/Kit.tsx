import { useMemo } from "react";
import {
  CanvasTexture,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  SRGBColorSpace,
  type Material,
  type Mesh,
  type Object3D,
} from "three";
import { C } from "../theme";
import sizes from "./kit.json";

/**
 * The film's one made object besides the phone and the mark: the Bitcoin coin
 * (blender/build_assets.py, kit.glb), with the film's own materials, and the dark floor
 * it falls on. Everything else in the film is the app's own interface in two dimensions.
 */

export const KIT = sizes;

/** Struck metal: never black, because the studio is always there to reflect. */
const metal = (tint: string, rough: number): MeshPhysicalMaterial =>
  new MeshPhysicalMaterial({
    color: tint,
    metalness: 1,
    roughness: rough,
    clearcoat: 0.25,
    clearcoatRoughness: 0.3,
    envMapIntensity: 1.25,
  });

const materials = (): Record<string, Material> => ({
  coin: metal(C.btc, 0.34),
  "coin relief": metal("#e2a67c", 0.2),
});

/**
 * The coin, as its own copy. `name` lets a shot find it again to move it between frames
 * (Stage, `move`).
 */
export const Coin: React.FC<{
  readonly kit: Object3D;
  readonly name?: string;
  readonly scale?: number;
}> = ({ kit, name, scale }) => {
  const object = useMemo(() => {
    const found = kit.getObjectByName("coin");
    if (!found) {
      throw new Error("The kit has no coin");
    }
    const copy = found.clone(true);
    const mine = materials();
    copy.traverse((child) => {
      const mesh = child as Mesh;
      if (!mesh.isMesh) {
        return;
      }
      const swap = (old: Material): Material => mine[old.name] ?? old;
      mesh.material = Array.isArray(mesh.material)
        ? mesh.material.map(swap)
        : swap(mesh.material);
    });
    // The copy gives up its name: a shot finds the group around it, once.
    copy.name = "";
    return copy;
  }, [kit]);
  return (
    <group name={name} scale={scale}>
      <primitive object={object} />
    </group>
  );
};

/** Calls `fn` for every object of that name: a thing and its reflection share one. */
export const each = (
  scene: Object3D,
  name: string,
  fn: (object: Object3D) => void,
): void => {
  scene.traverse((child) => {
    if (child.name === name) {
      fn(child);
    }
  });
};

const radial = (
  size: number,
  inner: number,
  from: string,
  to: string,
  under?: (paper: CanvasRenderingContext2D) => void,
): CanvasTexture => {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const paper = canvas.getContext("2d");
  if (paper) {
    under?.(paper);
    const fall = paper.createRadialGradient(
      size / 2,
      size / 2,
      size * inner,
      size / 2,
      size / 2,
      size * 0.5,
    );
    fall.addColorStop(0, from);
    fall.addColorStop(1, to);
    paper.fillStyle = fall;
    paper.fillRect(0, 0, size, size);
  }
  return new CanvasTexture(canvas);
};

const gridTexture = (): CanvasTexture => {
  const size = 1024;
  const texture = radial(
    size,
    0.08,
    "rgba(0,0,0,0)",
    "rgba(0,0,0,1)",
    (paper) => {
      paper.fillStyle = "#000";
      paper.fillRect(0, 0, size, size);
      paper.strokeStyle = "rgba(255,255,255,0.5)";
      paper.lineWidth = 1.2;
      const cells = 32;
      for (let i = 0; i <= cells; i++) {
        const at = (i / cells) * size;
        paper.beginPath();
        paper.moveTo(at, 0);
        paper.lineTo(at, size);
        paper.moveTo(0, at);
        paper.lineTo(size, at);
        paper.stroke();
      }
    },
  );
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = 16;
  return texture;
};

/**
 * The floor the coin falls on: dark glass at y = 0 with a faint grid that fades out.
 * The coin is drawn a second time upside down beneath it and seen through the glass,
 * which is what a reflection in a dark pane looks like.
 */
export const Floor: React.FC<{
  readonly size?: number;
  /** How strongly the floor shows what stands on it, from 0 to 1. */
  readonly shine?: number;
  readonly tint?: string;
  readonly children?: React.ReactNode;
}> = ({ size = 40, shine = 0.3, tint = C.accent, children }) => {
  const grid = useMemo(gridTexture, []);
  const fade = useMemo(() => radial(256, 0.12, "#fff", "#000"), []);
  // The pane is not lit at all: a lit floor seen at a low angle turns into a grey sheet
  // of highlight. It is simply dark, thinner towards its edge so that it has no horizon.
  const pane = useMemo(
    () =>
      new MeshBasicMaterial({
        color: "#050609",
        transparent: true,
        opacity: 1 - shine,
        alphaMap: fade,
        toneMapped: false,
      }),
    [shine, fade],
  );
  const lines = useMemo(
    () =>
      new MeshBasicMaterial({
        map: grid,
        color: tint,
        transparent: true,
        opacity: 0.16,
        depthWrite: false,
        toneMapped: false,
        blending: 2,
      }),
    [grid, tint],
  );
  return (
    <>
      {children}
      <group scale={[1, -1, 1]}>{children}</group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} material={pane} renderOrder={1}>
        <planeGeometry args={[size, size]} />
      </mesh>
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, 0.002, 0]}
        material={lines}
        renderOrder={2}
      >
        <planeGeometry args={[size * 0.6, size * 0.6]} />
      </mesh>
    </>
  );
};
