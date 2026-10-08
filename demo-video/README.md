# The RADAR reel

A 23-second advertisement for RADAR, made in Remotion: 1920 × 1080, 30 frames a second,
690 frames, cut to 120 beats a minute (15 frames a beat).

| # | Frames | Picture | Words |
| --- | --- | --- | --- |
| 1 | 0 to 74 | A Bitcoin price that will not keep still | Buy now? Or wait? |
| 2 | 75 to 134 | The radar line clears the frame; the mark draws itself; the camera goes through its ring | Meet RADAR. |
| 3 | 135 to 224 | A glide along the phone's metal edge; it swings round showing Home, with a blip for each thing held | Reads your account. Touches nothing. |
| 4 | 225 to 314 | The three market cards lift off the screen as panes of glass; the camera travels down the row | Calm. Calm. Normal. |
| 5 | 315 to 419 | One price is cut into the low and high of the week's range, and the outcomes rise between | Not a guess. A range. |
| 6 | 420 to 509 | The radar line again; the money ring, then the risk ring round it | 12% of your money. 62% of your risk. |
| 7 | 510 to 599 | The bar of what is held reshapes into the plan; the camera moves in on three prices lighting in turn | Your plan. Your next step. |
| 8 | 600 to 689 | Three lines, one a beat; then the mark | No tips. No trades. No promises. RADAR. It measures. You decide. |

The words of shots 4 and 6 are read from the fixtures, so they change if the figures do.

## Where things are

| Where | What |
| --- | --- |
| `src/shots.json` | The one place a shot's start and length are written |
| `src/timing.ts` | The beat, the film's words, and the curves everything moves on |
| `src/Reel.tsx` | One sequence a shot, each mounted a second early, over one ground |
| `src/shots/` | One file a shot |
| `src/Ground.tsx` | The dark ground and its one light, whose colour follows the subject and is never cut |
| `src/Sweep.tsx` | The radar line as a change of scene (shots 2 and 6) |
| `src/Words.tsx` | Type that arrives a word at a time out of a blur, with one accent colour |
| `src/ui/` | The app's interface rebuilt from `frontend/src` (`kit.tsx`), and its Home screen (`Home.tsx`) |
| `src/three/` | The 3D stage, the phone's materials, and the mark |
| `src/fixtures/` | The figures: `market.json` from the app's market pages, `portfolio.json` a made-up example |
| `blender/build_assets.py` | Builds the phone (`public/assets/phone.glb`) |
| `scripts/` | `stills.mjs` renders chosen frames; `sheet.py` lays them on one sheet |
| `ASSETS.md` | Every file from elsewhere, with its source and licence |

## Commands

Preview:

```bash
npm --prefix demo-video run dev
```

Render the film (from `demo-video/`):

```bash
npx remotion render Reel out/reel.mp4
```

Render chosen frames, or one frame a second for a contact sheet:

```bash
node scripts/stills.mjs out/look 100 172 380
```

```bash
node scripts/stills.mjs out/sheet every 30
```

Rebuild the phone:

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b -P demo-video/blender/build_assets.py
```

Photograph the film's Home screen again for the phone, after changing `src/ui/Home.tsx`
or a fixture:

```bash
npx remotion still Home public/ui/home.png --scale=3
```

## Rules this film keeps

- **Every moving thing is a function of the frame.** No CSS transitions or keyframes, no
  timers, nothing random. The interface in `src/ui/` takes its animated values as props.
- **Nothing from an account.** Market figures may come from the app's market pages.
  Portfolio figures are the made-up example in `fixtures/portfolio.json`, and the shots
  that use it say "Example portfolio". The phone's Home is the film's own rebuild showing
  that example, not a photograph of the running app.
- **Nothing downloaded goes in `public/` before it is in `ASSETS.md`.** CC0 only.
- **Remotion packages are pinned** to the version in `package.json`.

## Three things that bite

- **Load objects and pictures outside the 3D canvas** (`useAssets` in `three/assets.tsx`).
  A render hold placed inside the canvas comes too late and the first frames come out
  empty.
- **While rendering, the canvas only draws when told to.** After the reflections are set
  the scene is drawn once more by hand (`Studio` in `three/Stage.tsx`), or a render tab's
  first frame has black metal.
- **One 3D object can stand in only one scene.** Two shots are mounted at once around a
  cut, so the second shot to use the phone takes a copy of it (`shots/Cards.tsx`).

## How the blur is made

`three/Stage.tsx` draws a blurred frame at 28 moments across the time the shutter is open
and averages them on a plain canvas, which is the one that is seen. A shot therefore gives
its camera, and anything that moves fast, as functions of the frame (`camera`, `move`),
so they can be asked for moments between two frames.
