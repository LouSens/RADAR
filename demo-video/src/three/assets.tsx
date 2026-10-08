import { createContext, useContext, useEffect, useState } from "react";
import {
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
} from "remotion";
import {
  EquirectangularReflectionMapping,
  SRGBColorSpace,
  TextureLoader,
  type DataTexture,
  type Object3D,
  type Texture,
} from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";

/**
 * What the phone's screen shows (public/ui). `home` is the film's own rebuild of the
 * app's Home with the example portfolio, photographed from the Home composition.
 */
const SCREENS = ["home"] as const;
export type ScreenName = (typeof SCREENS)[number];

export interface Assets {
  /** The phone made by blender/build_assets.py. */
  readonly phone: Object3D;
  /** The studio the metal and glass reflect (see ASSETS.md). */
  readonly room: DataTexture;
  readonly screens: Readonly<Record<ScreenName, Texture>>;
}

const screen = async (name: ScreenName): Promise<Texture> => {
  const texture = await new TextureLoader().loadAsync(
    staticFile(`ui/${name}.png`),
  );
  texture.colorSpace = SRGBColorSpace;
  // The phone's screen was mapped in Blender, whose pictures start at the bottom.
  texture.flipY = false;
  texture.anisotropy = 16;
  return texture;
};

/**
 * Everything the 3D shots need, loaded before anything is drawn. Call this outside the
 * 3D canvas: a hold placed inside it comes too late, and the first frames render empty.
 */
export const useAssets = (): Assets | null => {
  const [assets, setAssets] = useState<Assets | null>(null);
  const [handle] = useState(() =>
    delayRender("Loading the phone, the studio and the screens"),
  );

  useEffect(() => {
    Promise.all([
      new GLTFLoader().loadAsync(staticFile("assets/phone.glb")),
      new HDRLoader().loadAsync(staticFile("hdri/studio_small_08_1k.hdr")),
      Promise.all(SCREENS.map(screen)),
    ])
      .then(([phone, room, screens]) => {
        room.mapping = EquirectangularReflectionMapping;
        setAssets({
          phone: phone.scene,
          room,
          screens: Object.fromEntries(
            SCREENS.map((name, i) => [name, screens[i]]),
          ) as Record<ScreenName, Texture>,
        });
        continueRender(handle);
      })
      .catch((error) => cancelRender(error));
  }, [handle]);

  return assets;
};

const AssetsContext = createContext<Assets | null>(null);

export const AssetsProvider = AssetsContext.Provider;

/**
 * The loaded assets, for a shot. Read this outside the 3D canvas and hand the parts in
 * as props: the canvas does not pass this context to what is drawn inside it.
 */
export const useLoaded = (): Assets | null => useContext(AssetsContext);
