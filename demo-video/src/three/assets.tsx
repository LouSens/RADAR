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

/** The app's cards that stand on glass in the film (public/cards, scripts/cards.py). */
const CARDS = ["range", "risk"] as const;
export type CardName = (typeof CARDS)[number];

export interface Assets {
  /** The phone made by blender/build_assets.py. */
  readonly phone: Object3D;
  /** The coin, the ingot, the stocks block, the chip and the numerals, by name. */
  readonly kit: Object3D;
  readonly cards: Readonly<Record<CardName, Texture>>;
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

const card = async (name: CardName): Promise<Texture> => {
  const texture = await new TextureLoader().loadAsync(
    staticFile(`cards/${name}.png`),
  );
  texture.colorSpace = SRGBColorSpace;
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
      new GLTFLoader().loadAsync(staticFile("assets/kit.glb")),
      Promise.all(CARDS.map(card)),
    ])
      .then(([phone, room, screens, kit, cards]) => {
        room.mapping = EquirectangularReflectionMapping;
        setAssets({
          phone: phone.scene,
          kit: kit.scene,
          cards: Object.fromEntries(
            CARDS.map((name, i) => [name, cards[i]]),
          ) as Record<CardName, Texture>,
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
