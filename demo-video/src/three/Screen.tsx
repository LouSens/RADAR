import { useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";
import { CanvasTexture, SRGBColorSpace } from "three";

export type Screens = Readonly<Record<string, CanvasTexture>>;

// The phone's screen, in metres, and how round its corners are (blender/build_assets.py).
const WIDTH = 0.068;
const HEIGHT = 0.148;
const CORNER = 0.0105 / WIDTH;

/**
 * Real pages of the app (public/ui/<name>.png, photographed by the Capture composition),
 * with their corners rounded to fit the phone. Call this outside the 3D canvas.
 */
export const useScreens = (names: readonly string[]): Screens | null => {
  const [screens, setScreens] = useState<Screens | null>(null);
  const [handle] = useState(() => delayRender("Loading the app's screens"));
  const key = names.join(",");

  useEffect(() => {
    Promise.all(
      key.split(",").map(
        (name) =>
          new Promise<readonly [string, CanvasTexture]>((resolve, reject) => {
            const image = new Image();
            image.onload = () => {
              const canvas = document.createElement("canvas");
              canvas.width = image.width;
              canvas.height = Math.round((image.width * HEIGHT) / WIDTH);
              const context = canvas.getContext("2d");
              if (!context) {
                reject(new Error("No 2D context"));
                return;
              }
              context.beginPath();
              context.roundRect(
                0,
                0,
                canvas.width,
                canvas.height,
                canvas.width * CORNER,
              );
              context.clip();
              context.drawImage(image, 0, 0);
              const texture = new CanvasTexture(canvas);
              texture.colorSpace = SRGBColorSpace;
              texture.anisotropy = 8;
              resolve([name, texture] as const);
            };
            image.onerror = () => reject(new Error(`Could not load ${name}`));
            image.src = staticFile(`ui/${name}.png`);
          }),
      ),
    )
      .then((loaded) => {
        setScreens(Object.fromEntries(loaded));
        continueRender(handle);
      })
      .catch((error) => cancelRender(error));
  }, [handle, key]);

  return screens;
};

/** A page of the app lying on the phone's glass. Place it inside the phone's group. */
export const Screen: React.FC<{
  readonly texture: CanvasTexture;
  readonly opacity?: number;
}> = ({ texture, opacity = 1 }) => (
  <mesh position={[0, 0, 0.0011]}>
    <planeGeometry args={[WIDTH, HEIGHT]} />
    <meshBasicMaterial
      map={texture}
      alphaTest={0.5}
      opacity={opacity}
      toneMapped={false}
    />
  </mesh>
);
