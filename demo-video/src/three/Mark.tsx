import { useMemo } from "react";
import {
  CurvePath,
  LineCurve3,
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

export const RING = { centre: at(15, 17), radius: 8.5 * UNIT } as const;
const LINE = [at(7.5, 21.5), at(12.5, 16.5), at(16, 19.5), at(24.5, 10)];
export const DOT = { centre: at(24.5, 10), radius: 2.4 * UNIT } as const;
const LINE_RADIUS = 1.2 * UNIT;
const RING_RADIUS = 0.6 * UNIT;

/** The accent, deepened: what the mark is made of under its glow. */
const BODY = "#0d7f99";

const SEGMENTS = 220;
const SIDES = 20;

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

export const Mark: React.FC<{
  /** How much of each part is drawn, from 0 to 1. */
  readonly ring: number;
  readonly line: number;
  readonly dot: number;
  /** How strongly the parts give off their own light. */
  readonly glow?: number;
}> = ({ ring, line, dot, glow = 1 }) => {
  const path = useMemo(linePath, []);
  const tube = useMemo(
    () => new TubeGeometry(path, SEGMENTS, LINE_RADIUS, SIDES, false),
    [path],
  );
  const drawn = Math.round(line * SEGMENTS);
  tube.setDrawRange(0, drawn * SIDES * 6);
  const tip = path.getPointAt(Math.min(Math.max(drawn / SEGMENTS, 0), 1));
  const arc = Math.max(ring, 0.0001) * Math.PI * 2;

  // A deep body under its own light: lit by the accent alone it washes out to white.
  const lit = (
    <meshStandardMaterial
      color={BODY}
      emissive={C.accent}
      emissiveIntensity={0.5 * glow}
      metalness={0.15}
      roughness={0.3}
      envMapIntensity={0.55}
    />
  );
  const ringEnd = new Vector3(
    RING.centre.x + Math.sin(arc) * RING.radius,
    RING.centre.y + Math.cos(arc) * RING.radius,
    0,
  );
  const dim = (
    <meshStandardMaterial
      color={BODY}
      emissive={C.accent}
      emissiveIntensity={0.16 * glow}
      metalness={0.7}
      roughness={0.28}
      envMapIntensity={0.8}
    />
  );

  return (
    <group>
      {ring > 0 && (
        // Drawn clockwise from twelve o'clock, the way the radar line turns.
        <mesh
          position={RING.centre}
          rotation={[0, 0, -Math.PI / 2]}
          scale={[-1, 1, 1]}
        >
          <torusGeometry args={[RING.radius, RING_RADIUS, 20, 160, arc]} />
          {dim}
        </mesh>
      )}
      {ring > 0 && ring < 1 && (
        <mesh position={ringEnd}>
          <sphereGeometry args={[RING_RADIUS, 20, 14]} />
          {dim}
        </mesh>
      )}
      {drawn > 0 && (
        <group position={[0, 0, 0.14]}>
          <mesh geometry={tube}>{lit}</mesh>
          <mesh position={LINE[0]}>
            <sphereGeometry args={[LINE_RADIUS, 24, 16]} />
            {lit}
          </mesh>
          <mesh position={tip}>
            <sphereGeometry args={[LINE_RADIUS, 24, 16]} />
            {lit}
          </mesh>
        </group>
      )}
      {dot > 0 && (
        <mesh position={[DOT.centre.x, DOT.centre.y, 0.14]} scale={dot}>
          <sphereGeometry args={[DOT.radius, 48, 32]} />
          {lit}
        </mesh>
      )}
    </group>
  );
};
