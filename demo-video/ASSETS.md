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
| `public/assets/kit.glb` | The Bitcoin coin: struck with the Bitcoin sign on both faces, with a reeded edge. The sign is the letter B from Blender's own bundled font (Bfont, which ships with Blender under its free licence) with the sign's four short strokes added | `blender/build_assets.py` (Blender 5.0) |
| `public/sfx/*.wav` | Every sound in the film: short effects and a room tone. Generated, not recorded or downloaded | `sound/make_sfx.py` (numpy) |
| `public/desk/*.png` | The app's pages at desktop size (and Home at phone size, which is on the phone's screen in shot 9), showing the made-up example portfolio and recorded market data. The desktop pages are reference for the pieces the film draws itself. Never photographed from the app that shows an account | `scripts/capture.mjs`, from the app fed by `mock-api/server.mjs` |
| `mock-api/data/example/*` | The example account as the app's API would give it: worth, holdings, risk, plan, what to do now, the brief, and Bitcoin's "before you buy" check with no account record | `mock-api/make_account.py`: the app's own code run on the example holdings and stored market prices. The stored portfolio is never read |
| `src/fixtures/fall.json` | The hourly closes of Bitcoin's largest recent down day against a usual day, and that day's figures | Read from the app's market data (`GET /assets/btc-usd/moves` and hourly bars) on 2026-10-08 |
| `mock-api/example.json` | A made-up example portfolio: invented holdings and an invented plan | Written on 2026-10-08 |
| `src/fixtures/film.json` | Every figure in the film: the three markets, Bitcoin's range, its last thirty days, its place in each period, the calendar, and the example portfolio as the app works it out | `scripts/fixtures.mjs`, from the mock API's data, on 2026-10-08 |

The mark is drawn in code (`src/three/Mark.tsx`) from the shapes in the app's own
`RadarMark`.
