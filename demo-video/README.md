# The RADAR reel

A 24-second advertisement for RADAR, made in Remotion: 1920 × 1080, 30 frames a second,
710 frames, cut to 120 beats a minute (15 frames a beat). Its words say what RADAR does
and has. It has sound effects and no music.

| # | Frames | Picture | Headline | Small line |
| --- | --- | --- | --- | --- |
| 1 | 0 to 74 | A Bitcoin price that will not keep still | Buy now? Or wait? | |
| 2 | 75 to 134 | The radar line clears the frame; the mark draws itself; the camera goes through its ring | Meet RADAR. | |
| 3 | 135 to 224 | A glide along the phone's metal edge; it swings round showing Home, with a blip for each thing held | Every coin you hold. Live. | Synced from Binance by itself. |
| 4 | 225 to 314 | The three market cards lift off the screen as panes of glass; the camera travels down the row | How every market feels today. | |
| 5 | 315 to 419 | One price is cut into the low and high of the week's range, and the outcomes rise between | Next week's range. Today. | From 10,000 simulated weeks. |
| 6 | 420 to 509 | The radar line again; one number in the middle of its rings counts to Bitcoin's share of the money, then on to its share of the risk | Of your money. Of your risk. (12%, then 62%) | |
| 7 | 510 to 599 | The card with the next step, full width; the bar of shares becomes the plan; three blips land on three prices, one a beat | What to buy next. And at what price. | From the plan you set. |
| 8 | 600 to 709 | Three phrases, one a beat; they leave together and the end card arrives in the middle: the mark, the name, what RADAR is | Your account. Your risk. Your plan. RADAR. An analyst for everything you own. | |

The figure of shot 6 is read from the example portfolio, so it changes if that does.

## Type

All of it is in `src/Type.tsx`, and there is nothing else:

- **Three sizes.** Headline: Inter Bold, 140, tracking -3%. Hero number: 260, with every
  digit the same width. Small line: Inter Medium, 40, in `#9ea2b0`.
- **One grid.** Headlines start at a left margin of 128, in the upper third. Two
  exceptions: shot 3's words stand beside the phone, level with its top edge, and shot
  8's end card is centred, with its second line at 80, the only use of that size.
- **One way in and out.** Each word rises out of a mask at the foot of its line over 8
  frames, half a beat after the word before, and a line leaves by rising out through the
  top. Type is never faded and never blurred.
- **One accent word a line**, in the colour of what is on screen.
- In shots 3 and 4 the headline is behind the phone and the panes, which pass in front.

Words inside a rebuilt piece of the app (a card's label, a chart's ends) keep the app's
own sizes: they are the interface, not the film's type.

## Where things are

| Where | What |
| --- | --- |
| `src/shots.json` | The one place a shot's start and length are written |
| `src/timing.ts` | The beat, the film's words, and the curves everything moves on |
| `src/Reel.tsx` | One sequence a shot, each mounted a second early, over one ground |
| `src/shots/` | One file a shot |
| `src/Ground.tsx` | The dark ground and its one light, whose colour follows the subject and is never cut |
| `src/Sound.tsx` | Every sound cue, each taking its frame from the animation it belongs to; the mix is the `LEVEL` table |
| `sound/make_sfx.py` | Makes every sound from arithmetic (numpy only) into `public/sfx/` |
| `src/Sweep.tsx` | The radar line as a change of scene (shots 2 and 6) |
| `src/Type.tsx` | The film's type: three sizes, one grid, words rising out of a mask |
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

Make the sounds again:

```bash
python demo-video/sound/make_sfx.py
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

## Photographing the app

Every desktop page of the running app shows the account in its sidebar, so that app is
never photographed. The stills in `public/desk/` come from the same frontend fed by a
stand-in for the API:

```
node mock-api/record.mjs                      # market data only, by GET, from the running API
uv run python mock-api/make_account.py        # the example account, from ../ (the repo root)
node mock-api/server.mjs                      # the stand-in, on 127.0.0.1:8010
RADAR_API_URL=http://127.0.0.1:8010 npm --prefix ../frontend run dev -- --port 5180
node scripts/capture.mjs                      # every still; name some to redo only those
```

- `record.mjs` refuses any address that names the portfolio, the account, the brief or
  the system page, and keeps only the three markets the app always follows: the full
  list of markets also names what the account holds. What it records
  (`mock-api/data/recorded/`) is not committed.
- `make_account.py` works the example account out with the app's own code from the
  holdings in `src/fixtures/portfolio.json`. It opens the database read-only and never
  reads the stored portfolio, plan or account record.
- `capture.mjs` will not take a still unless the app it is pointed at is showing the
  example portfolio.
- Look at every still before using it: no loading placeholders, no fault, no figure
  that is not the example's.

## Rules this film keeps

- **Every moving thing is a function of the frame.** No CSS transitions or keyframes, no
  timers, nothing random. The interface in `src/ui/` takes its animated values as props.
- **Nothing from an account.** Market figures may come from the app's market pages.
  Portfolio figures are the made-up example in `fixtures/portfolio.json`, and the shots
  that use it say "Example portfolio". The phone's Home is the film's own rebuild showing
  that example, not a photograph of the running app.
- **Nothing downloaded goes in `public/` before it is in `ASSETS.md`.** CC0 only.
- **No music and no downloaded audio.** Sounds are generated, each at its own level; the
  whole mix is never normalised. The room tone is turned off by `ROOM` in `Sound.tsx`.
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
