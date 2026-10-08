# The RADAR film: "Payday"

A 30-second app ad in seven beats. Motion graphics made in Remotion, with a small set of
3D objects made in Blender.

| Beat | Time | Copy | Built |
|---|---|---|---|
| 1 | 0:00 to 0:03 | Payday. Now what? | Yes |
| 2 | 0:03 to 0:07 | Everyone has a tip. | Yes |
| 3 | 0:07 to 0:10 | Meet RADAR. It starts with what you already own. | Yes |
| 4 | 0:10 to 0:15 | Where your money sits. | No |
| 5 | 0:15 to 0:20 | Where your risk sits. | No |
| 6 | 0:20 to 0:25 | And where this month's money goes. | No |
| 7 | 0:25 to 0:30 | No tips. No trades. · RADAR. It measures. You decide. | No |

## Where things are

- `blender/build_assets.py` makes the 3D objects, each alone, into `public/assets/` as a
  `.glb` and a `.png`. That is all Blender does: no shots and no camera moves.
- `src/shots.json` holds each beat's start and length; `src/timing.ts` holds the copy.
- `src/Opening.tsx` is beats 1 to 3 as one scene. `src/three/` loads the objects and
  lights them. `src/Words.tsx` is the large type that arrives a word at a time.
- `public/ui/` holds real pages of the app, photographed at phone size by the `Capture`
  composition (`npx remotion still Capture public/ui/markets.png --props=...`, with the
  app running). Only pages of market data are kept there: nothing from an account.

```bash
npm --prefix demo-video run dev
```

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b -P demo-video/blender/build_assets.py
```

## Two things that bite

- **Load objects outside the 3D canvas** (`useObjects`). A render hold placed inside the
  canvas comes too late and the first frames come out empty.
- **While rendering, the canvas only draws when told to.** After setting the reflections
  the scene must be advanced once by hand (`Studio`), or each render tab's first frame is
  drawn without them and the metal is black.

`docs/DEMO_STORYBOARD.md` and `docs/DEMO_STAGING.md` describe an earlier concept, a
calibration laboratory, which was set aside for this one.
