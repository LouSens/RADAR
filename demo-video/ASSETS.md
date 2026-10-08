# Assets in the reel

The repository is public. Every file here that was not made in this repository is listed
with where it came from and its licence. Nothing goes in `public/` before it is listed.

## From elsewhere

| File | What | Source | Author | Licence |
| --- | --- | --- | --- | --- |
| `public/hdri/studio_small_08_1k.hdr` | The studio the metal and glass reflect | https://polyhaven.com/a/studio_small_08 (1k HDR, md5 `de3ba64222895aca876b1d1c2e0cf81a`) | Sergej Majboroda | CC0 1.0 (https://polyhaven.com/license) |

Inter is loaded at render time by `@remotion/google-fonts` and is not stored here (SIL
Open Font License 1.1).

## Made here

| File | What | Made by |
| --- | --- | --- |
| `public/assets/phone.glb` | A generic phone: metal frame, glass, camera bump, no maker's shapes or marks | `blender/build_assets.py` (Blender 5.0) |
| `public/ui/*.png` | Pages of the running app at phone size. Market data only | The `Capture` composition |
| `src/fixtures/market.json` | Prices, a week of hourly closes, states and the week's range for the three markets | Read from the app's market pages on 2026-10-08 |

The mark is drawn in code (`src/three/Mark.tsx`) from the shapes in the app's own
`RadarMark`.
