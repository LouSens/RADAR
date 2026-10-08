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
| `public/assets/kit.glb` | The things the figures become: a coin struck with the Bitcoin sign, a gold ingot, a block of rising bars, a cash chip, and solid numerals. No maker's shapes or marks. The numerals are cut from Blender's own bundled font (Bfont, which ships with Blender under its free licence); the film's type everywhere else is Inter | `blender/build_assets.py` (Blender 5.0) |
| `public/cards/*.png` | Cards of the app cut from the stills in `public/desk/`, for the faces of the glass cards | `scripts/cards.py` |
| `public/sfx/*.wav` | Every sound in the film: short effects and a room tone. Generated, not recorded or downloaded | `sound/make_sfx.py` (numpy) |
| `public/ui/home.png` | The film's own rebuild of the app's Home, showing the made-up example portfolio | The `Home` composition (`src/ui/Home.tsx`) |
| `public/ui/*.png` (the rest) | Pages of the running app at phone size, kept as reference. Market data only | The `Capture` composition |
| `public/desk/*.png` | The app's pages at desktop size (and Home at phone size), showing the made-up example portfolio and recorded market data. Never photographed from the app that shows an account | `scripts/capture.mjs`, from the app fed by `mock-api/server.mjs` |
| `mock-api/data/example/*` | The example account as the app's API would give it: worth, holdings, risk, plan, what to do now, the brief, and Bitcoin's "before you buy" check with no account record | `mock-api/make_account.py`: the app's own code run on the example holdings and stored market prices. The stored portfolio is never read |
| `src/fixtures/fall.json` | The hourly closes of Bitcoin's largest recent down day against a usual day, and that day's figures | Read from the app's market data (`GET /assets/btc-usd/moves` and hourly bars) on 2026-10-08 |
| `src/fixtures/portfolio.json` | A made-up example portfolio: invented holdings, with risk shares and a usual week's move worked out from daily market closes the way the app does | Written on 2026-10-08 |
| `src/fixtures/market.json` | Prices, a week of hourly closes, states and the week's range for the three markets | Read from the app's market pages on 2026-10-08 |

The mark is drawn in code (`src/three/Mark.tsx`) from the shapes in the app's own
`RadarMark`.
