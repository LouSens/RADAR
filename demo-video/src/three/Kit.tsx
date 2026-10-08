import { useMemo } from "react";
import {
  CanvasTexture,
  Color,
  DoubleSide,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  SRGBColorSpace,
  type Material,
  type Mesh,
  type Object3D,
  type Texture,
} from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { C } from "../theme";
import sizes from "./kit.json";

/**
 * The things the film's figures become: the objects made in Blender
 * (blender/build_assets.py, kit.glb) with the film's own materials, and the plain glass
 * ones whose size depends on a figure (cards, bars, the floor), which are made here.
 * A holding keeps the colour it has in the app: copper, gold, steel, and grey for cash.
 */

export const KIT = sizes;

const CASH = "#8fa3ad";

/** Clear glass with a tint: it lets the scene through, and its edges catch the room. */
export const glass = (
  tint: string,
  options: { readonly glow?: number; readonly rough?: number } = {},
): MeshPhysicalMaterial =>
  new MeshPhysicalMaterial({
    color: tint,
    metalness: 0,
    roughness: options.rough ?? 0.15,
    transmission: 0.82,
    thickness: 0.6,
    ior: 1.45,
    attenuationColor: new Color(tint),
    attenuationDistance: 1.4,
    clearcoat: 1,
    clearcoatRoughness: 0.08,
    envMapIntensity: 1.3,
    emissive: new Color(tint),
    emissiveIntensity: options.glow ?? 0.06,
  });

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
  gold: metal(C.gold, 0.3),
  // Lit a little from within: clear glass on a dark floor would not be seen at all.
  stock: glass(C.stock, { glow: 0.42, rough: 0.2 }),
  cash: new MeshPhysicalMaterial({
    color: CASH,
    metalness: 0.15,
    roughness: 0.72,
    clearcoat: 0.15,
    clearcoatRoughness: 0.6,
  }),
  "cash mark": new MeshStandardMaterial({ color: "#c9d6dc", roughness: 0.5 }),
  numeral: new MeshPhysicalMaterial({
    color: "#eef0f6",
    metalness: 0,
    roughness: 0.22,
    clearcoat: 1,
    clearcoatRoughness: 0.1,
    envMapIntensity: 1.1,
  }),
});

export type PieceName =
  | "coin"
  | "ingot"
  | "stocks"
  | "chip"
  | "dollar"
  | "comma"
  | "percent"
  | `d${number}`;

/**
 * One object of the kit, as its own copy, so that it can stand in several places at
 * once. `name` lets a shot find it again to move it between frames (Stage, `move`).
 */
export const Piece: React.FC<{
  readonly kit: Object3D;
  readonly piece: PieceName;
  readonly name?: string;
  readonly position?: readonly [number, number, number];
  readonly rotation?: readonly [number, number, number];
  readonly scale?: number | readonly [number, number, number];
  readonly material?: Material;
}> = ({ kit, piece, name, position, rotation, scale, material }) => {
  const object = useMemo(() => {
    const found = kit.getObjectByName(piece);
    if (!found) {
      throw new Error(`The kit has no ${piece}`);
    }
    const copy = found.clone(true);
    const mine = materials();
    copy.traverse((child) => {
      const mesh = child as Mesh;
      if (!mesh.isMesh) {
        return;
      }
      const swap = (old: Material): Material =>
        material ?? mine[old.name] ?? old;
      mesh.material = Array.isArray(mesh.material)
        ? mesh.material.map(swap)
        : swap(mesh.material);
    });
    // The copy gives up its name: a shot finds the group around it, once.
    copy.name = "";
    return copy;
  }, [kit, piece, material]);
  return (
    <group
      name={name}
      position={position as [number, number, number] | undefined}
      rotation={rotation as [number, number, number] | undefined}
      scale={scale as number | [number, number, number] | undefined}
    >
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

const gridTexture = (): CanvasTexture => {
  const size = 1024;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const paper = canvas.getContext("2d");
  if (paper) {
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
    // The grid fades out well before the floor's edge.
    const fall = paper.createRadialGradient(
      size / 2,
      size / 2,
      size * 0.08,
      size / 2,
      size / 2,
      size * 0.5,
    );
    fall.addColorStop(0, "rgba(0,0,0,0)");
    fall.addColorStop(1, "rgba(0,0,0,1)");
    paper.fillStyle = fall;
    paper.fillRect(0, 0, size, size);
  }
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = 16;
  return texture;
};

const fadeTexture = (): CanvasTexture => {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const paper = canvas.getContext("2d");
  if (paper) {
    const fall = paper.createRadialGradient(
      size / 2,
      size / 2,
      size * 0.12,
      size / 2,
      size / 2,
      size * 0.5,
    );
    fall.addColorStop(0, "#fff");
    fall.addColorStop(1, "#000");
    paper.fillStyle = fall;
    paper.fillRect(0, 0, size, size);
  }
  return new CanvasTexture(canvas);
};

/**
 * The floor: dark glass at y = 0 with a faint grid that fades out. What stands on it is
 * drawn a second time upside down beneath it and seen through the glass, which is what a
 * reflection in a dark pane looks like.
 */
export const Floor: React.FC<{
  readonly size?: number;
  /** How strongly the floor shows what stands on it, from 0 to 1. */
  readonly shine?: number;
  readonly tint?: string;
  readonly children?: React.ReactNode;
}> = ({ size = 40, shine = 0.3, tint = C.accent, children }) => {
  const grid = useMemo(gridTexture, []);
  const fade = useMemo(fadeTexture, []);
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

/**
 * A card of the app on thick glass: a rounded slab with bevelled edges, the real card
 * (cut from a photographed page) on its face, and dark glass on its back. It stands in
 * the XY plane facing +Z, centred on its own middle.
 */
export const Card: React.FC<{
  readonly face: Texture;
  readonly width: number;
  readonly name?: string;
  readonly position?: readonly [number, number, number];
  readonly rotation?: readonly [number, number, number];
  readonly scale?: number;
  /** How bright the face is, from 0 to 1. */
  readonly lit?: number;
}> = ({ face, width, name, position, rotation, scale, lit = 1 }) => {
  const picture = face.image as { width: number; height: number };
  const height = (width * picture.height) / picture.width;
  const depth = width * 0.04;
  const slab = useMemo(
    () => new RoundedBoxGeometry(width, height, depth, 6, depth * 0.45),
    [width, height, depth],
  );
  const body = useMemo(
    () =>
      new MeshPhysicalMaterial({
        color: "#12151b",
        metalness: 0.1,
        roughness: 0.15,
        transmission: 0.35,
        thickness: depth,
        clearcoat: 1,
        clearcoatRoughness: 0.06,
        envMapIntensity: 1.4,
      }),
    [depth],
  );
  const front = useMemo(
    () => new MeshBasicMaterial({ map: face, toneMapped: false, side: DoubleSide }),
    [face],
  );
  const sheen = useMemo(
    () =>
      new MeshPhysicalMaterial({
        color: "#000000",
        roughness: 0.05,
        transparent: true,
        opacity: 0.06,
        envMapIntensity: 1.6,
        depthWrite: false,
      }),
    [],
  );
  front.color.setScalar(lit);
  const inset = depth * 0.5;
  return (
    <group
      name={name}
      position={position as [number, number, number] | undefined}
      rotation={rotation as [number, number, number] | undefined}
      scale={scale}
    >
      <mesh geometry={slab} material={body} />
      <mesh position={[0, 0, depth / 2 + 0.0015]} material={front}>
        <planeGeometry args={[width - inset, height - inset]} />
      </mesh>
      <mesh position={[0, 0, depth / 2 + 0.003]} material={sheen}>
        <planeGeometry args={[width - inset, height - inset]} />
      </mesh>
    </group>
  );
};

const text = (value: number, unit: "dollar" | "percent"): PieceName[] => {
  const digits = Math.round(value).toLocaleString("en-US");
  const glyphs = [...digits].map(
    (c): PieceName => (c === "," ? "comma" : (`d${c}` as PieceName)),
  );
  return unit === "dollar" ? ["dollar", ...glyphs] : [...glyphs, "percent"];
};

const advance = (glyph: PieceName): number =>
  glyph === "comma"
    ? KIT.widths.comma * 1.5
    : glyph === "dollar"
      ? KIT.widths.dollar * 1.12
      : glyph === "percent"
        ? KIT.widths.percent * 1.08
        : KIT.cell;

/** How wide a figure is at a height of one unit. */
export const figureWidth = (value: number, unit: "dollar" | "percent"): number =>
  text(value, unit).reduce((sum, glyph) => sum + advance(glyph), 0);

/**
 * A figure as solid numerals standing on y = 0, centred on x = 0, one unit tall. Every
 * digit takes the same width, so a figure that counts does not shake.
 */
export const Numerals: React.FC<{
  readonly kit: Object3D;
  readonly value: number;
  readonly unit?: "dollar" | "percent";
  readonly name?: string;
  readonly position?: readonly [number, number, number];
  readonly rotation?: readonly [number, number, number];
  readonly scale?: number;
  readonly material?: Material;
}> = ({ kit, value, unit = "dollar", name, position, rotation, scale, material }) => {
  const glyphs = text(value, unit);
  const whole = glyphs.reduce((sum, glyph) => sum + advance(glyph), 0);
  let x = -whole / 2;
  return (
    <group
      name={name}
      position={position as [number, number, number] | undefined}
      rotation={rotation as [number, number, number] | undefined}
      scale={scale}
    >
      {glyphs.map((glyph, i) => {
        const wide = advance(glyph);
        const at = x + wide / 2;
        x += wide;
        return (
          <Piece
            key={`${i}-${glyph}`}
            kit={kit}
            piece={glyph}
            material={material}
            // The comma is made taller and hangs below the line, so that at a low angle
            // it is not read as a point.
            position={[at, glyph === "comma" ? -0.15 : 0, 0]}
            scale={glyph === "comma" ? [1.25, 2.2, 1] : undefined}
          />
        );
      })}
    </group>
  );
};
