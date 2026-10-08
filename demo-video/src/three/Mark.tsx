import { useMemo } from "react";
import {
  CurvePath,
  LineCurve3,
  MeshStandardMaterial,
  QuadraticBezierCurve3,
  TubeGeometry,
  Vector3,
} from "three";
import { C } from "../theme";

/**
 * RADAR's mark as three objects that can be drawn in turn: the ring, the rising line and
 * the dot it ends on. The shapes are the ones in the app (RadarMark in Layout.tsx, a box
 * of 32), brought to the film's units and centred on the box.
 */
const UNIT = 0.1;
const at = (x: number, y: number, z = 0): Vector3 =>
  new Vector3((x - 16) * UNIT, -(y - 16) * UNIT, z);

/**
 * Stroke widths on the logo's box of 32. The logo's line is 2.4 and its ring 1.5; a lit
 * tube with a halo reads heavier than a flat stroke of the same width, so these are a
 * little under.
 */
const LINE_STROKE = 1.9;
const RING_STROKE = 1.0;
const DOT_RADIUS = 2.1;

export const RING = { centre: at(15, 17), radius: 8.5 * UNIT } as const;
const LINE = [at(7.5, 21.5), at(12.5, 16.5), at(16, 19.5), at(24.5, 10)];
const DOT = { centre: at(24.5, 10), radius: DOT_RADIUS * UNIT } as const;
const LINE_RADIUS = (LINE_STROKE / 2) * UNIT;
const RING_RADIUS = (RING_STROKE / 2) * UNIT;

const SEGMENTS = 220;
const SIDES = 24;

/** The line's path, with its two corners eased as a round join would. */
const linePath = (): CurvePath<Vector3> => {
  const path = new CurvePath<Vector3>();
  const ease = 0.07;
  let from = LINE[0];
  for (let i = 1; i < LINE.length; i++) {
    const corner = LINE[i];
    const next = LINE[i + 1];
    if (!next) {
      path.add(new LineCurve3(from, corner));
      break;
    }
    const before = corner.clone().add(from.clone().sub(corner).setLength(ease));
    const after = corner.clone().add(next.clone().sub(corner).setLength(ease));
    path.add(new LineCurve3(from, before));
    path.add(new QuadraticBezierCurve3(before, corner, after));
    from = after;
  }
  return path;
};

/**
 * A lit tube: a deep core that gives off the accent, and an edge that brightens where the
 * surface turns away from the eye, as the wall of a glass tube does.
 */
const tube = (core: number, edge: number): MeshStandardMaterial => {
  const material = new MeshStandardMaterial({
    color: "#0a6f88",
    emissive: C.accent,
    emissiveIntensity: core,
    metalness: 0.1,
    roughness: 0.16,
    envMapIntensity: 0.9,
  });
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      `#include <emissivemap_fragment>
       float turned = 1.0 - saturate(dot(normalize(normal), normalize(vViewPosition)));
       totalEmissiveRadiance += vec3(0.62, 0.93, 1.0) * pow(turned, 2.2) * ${edge.toFixed(2)};`,
    );
  };
  return material;
};

export const Mark: React.FC<{
  /** How much of each part is drawn, from 0 to 1. */
  readonly ring: number;
  readonly line: number;
  readonly dot: number;
}> = ({ ring, line, dot }) => {
  const path = useMemo(linePath, []);
  const stroke = useMemo(
    () => new TubeGeometry(path, SEGMENTS, LINE_RADIUS, SIDES, false),
    [path],
  );
  const lit = useMemo(() => tube(0.42, 1.5), []);
  const dim = useMemo(() => tube(0.14, 0.9), []);

  const drawn = Math.round(line * SEGMENTS);
  stroke.setDrawRange(0, drawn * SIDES * 6);
  const tip = path.getPointAt(Math.min(Math.max(drawn / SEGMENTS, 0), 1));
  const arc = Math.max(ring, 0.0001) * Math.PI * 2;
  const ringEnd = new Vector3(
    RING.centre.x + Math.sin(arc) * RING.radius,
    RING.centre.y + Math.cos(arc) * RING.radius,
    0,
  );

  return (
    <group>
      {ring > 0 && (
        // Drawn clockwise from twelve o'clock, the way the radar line turns.
        <mesh
          position={RING.centre}
          rotation={[0, 0, -Math.PI / 2]}
          scale={[-1, 1, 1]}
          material={dim}
        >
          <torusGeometry args={[RING.radius, RING_RADIUS, 24, 200, arc]} />
        </mesh>
      )}
      {ring > 0 && ring < 1 && (
        <mesh position={ringEnd} material={dim}>
          <sphereGeometry args={[RING_RADIUS, 20, 14]} />
        </mesh>
      )}
      {drawn > 0 && (
        <group position={[0, 0, 0.12]}>
          <mesh geometry={stroke} material={lit} />
          <mesh position={LINE[0]} material={lit}>
            <sphereGeometry args={[LINE_RADIUS, 24, 16]} />
          </mesh>
          <mesh position={tip} material={lit}>
            <sphereGeometry args={[LINE_RADIUS, 24, 16]} />
          </mesh>
        </group>
      )}
      {dot > 0 && (
        <mesh
          position={[DOT.centre.x, DOT.centre.y, 0.12]}
          scale={dot}
          material={lit}
        >
          <sphereGeometry args={[DOT.radius, 48, 32]} />
        </mesh>
      )}
    </group>
  );
};
