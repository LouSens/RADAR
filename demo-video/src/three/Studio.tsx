import { useThree } from "@react-three/fiber";
import { useEffect } from "react";
import { PMREMGenerator } from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/** Where the objects stand: the top of the unseen surface that takes their shadows. */
export const FLOOR = -0.07;

/**
 * The light every object is seen in: soft surroundings for the metal to reflect, one
 * key from above and to the left as in the app, and a surface that shows only shadow.
 */
export const Studio: React.FC<{ readonly onReady: () => void }> = ({
  onReady,
}) => {
  const { gl, scene, advance } = useThree();

  useEffect(() => {
    const maker = new PMREMGenerator(gl);
    scene.environment = maker.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 1.1;
    maker.dispose();
    // While rendering, the canvas draws only when told to. Draw once more with the
    // reflections in place, and only then let the frame go.
    advance(performance.now());
    onReady();
  }, [advance, gl, onReady, scene]);

  return (
    <>
      <directionalLight
        position={[-0.7, 1.3, 0.9]}
        intensity={3.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-0.9}
        shadow-camera-right={0.9}
        shadow-camera-top={0.9}
        shadow-camera-bottom={-0.9}
        shadow-camera-near={0.1}
        shadow-camera-far={4}
        shadow-radius={9}
        shadow-bias={-0.0004}
      />
      <directionalLight
        position={[0.9, 0.4, -0.6]}
        intensity={0.9}
        color="#bfeaf5"
      />
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, FLOOR, 0]}
        receiveShadow
      >
        <planeGeometry args={[6, 6]} />
        {/* It must not hide what stands behind or below it: only shadow shows. */}
        <shadowMaterial opacity={0.2} depthWrite={false} />
      </mesh>
    </>
  );
};
