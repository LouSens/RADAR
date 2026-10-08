# The RADAR reel

A 32-second advertisement for RADAR, made in Remotion: 1920 × 1080, 30 frames a second,
960 frames, on a beat of 15 frames. One situation: Bitcoin falls, and the questions a
holder asks are each answered by the app. It has sound effects and no music.

**Three things are objects** (3D): the Bitcoin coin, the mark and the phone. **All the
data is the app's own interface in two dimensions**, rebuilt from `frontend/src` and
moving. The film is one chain of changes: each picture turns into the next, and nothing
goes back to Home between questions.

| # | Frames | Question | Picture |
| --- | --- | --- | --- |
| 1 | 0 to 114 | Bitcoin fell 2.6%. Sell? Hold? Buy more? | The coin spins on its edge, falls and wobbles; each word knocks it. The price falls through the day's real hours. The coin comes up on to its rim, spins round and stops facing the camera; then the words leave and the camera goes in |
| 2 | 115 to 249 | Meet RADAR. | The coin's rim is the mark's ring: the mark's colour comes in from the rim and the face goes from the middle out, so no frame is grey. The radar's line turns once inside the ring, the rising line is drawn, the dot lands. The mark lands as the logo of the sidebar, Home builds itself round it and is held whole for a second |
| 3 | 250 to 354 | Why did it fall? | The camera pushes into Home's Bitcoin card; its line stretches to the frame's width, falls flat, and thirty days grow about it as bars at their true scale; a crosshair slides to the day, its bar drops in red, its figures pop up |
| 4 | 355 to 444 | Is this price high or low? | The bars fall flat into a line and the line splits into five range bars; a bead slides to its place in each |
| 5 | 445 to 549 | How far could it go? | The five beads fly together and the price rises out of them; it is cut into the low and high of the week's range; the outcomes grow between |
| 6 | 550 to 654 | How risky is my mix? | The outcomes slide sideways into one thick bar; it fills by money (12, 4, 24, 60), then the same bar is weighed again by risk and Bitcoin's share pushes out to 67% |
| 7 | 655 to 759 | So what do I buy? | That bar thins into the plan bar, Now then Your plan; the ladder's line comes down out of its end and runs along under it; three coins drop on to its three prices |
| 8 | 760 to 824 | What's coming up? | The ladder's line swings up into the calendar's timeline and the rows hang off it; the Fed's count of days rolls down; the rows fly to their places in Home's own card as Home comes back round them |
| 9 | 825 to 899 | On your desk. On your phone. | The phone comes up first and Home steps aside; the sidebar becomes the capsule of places; the cards go across one at a time and arrive on the phone's screen; the phone stands still for a second |
| 10 | 900 to 959 | | A fast turn of the radar's line; the mark, RADAR., An analyst for everything you own. |

**Proof.** Near the end of shots 3 to 7 the picture pulls back and the answer is seen to
be a card of the app, on its page: in a desktop window (shots 3 and 6) or on the phone
(shots 4, 5 and 7). The phone is close, 85% of the frame's height, its page scrolled to the card. As the
answer comes out of its card the device drops away from the camera and is gone before
the answer starts to turn into the next (`src/Chain.tsx`, `src/Devices.tsx`). The pages are built from the app's own pieces
with the example portfolio; they are not photographs. Shot 8 is proved on Home itself.

**The lock.** Each answer is marked by four corners in the accent that start wide of it
and snap in to frame it, with a soft tick. There is no ring, ripple or tap anywhere.

**Questions** rise in the space beside their answer, above it or below it by turns, stand
still, and have left before the answer pulls back. Nothing crosses a question, and
every line of copy is whole on screen for at least 20 frames.

**Every figure is true.** Market figures are the app's own, recorded from its market
addresses; shot 1's fall is the recent day on which Bitcoin fell furthest against a
usual day. Portfolio figures are a made-up example, worked out by the app's own code,
and say "Example portfolio".

## Type

The film's own type is in `src/Type.tsx`:

- **A question** is Inter Bold at 96, tracking -3%: it rises a word at a time out of a
  mask where it will stand, and leaves by rising out through the top. Shot 1's lines
  and the last two are larger and centred.
- **One accent word a question**, never two.
- **The end card** is centred: the name at 140, and one line at 80.
- Type is never faded and never blurred, and nothing covers a question at rest.

Words and numbers inside a piece of the app keep the app's own sizes, enlarged with the
piece: they are the interface, not the film's type. Every number uses tabular figures,
and a number that changes counts as a meter does (`Ticker` in `src/ui/motion.tsx`).

## Where things are

| Where | What |
| --- | --- |
| `src/shots.json` | The one place a shot's start and length are written |
| `src/timing.ts` | The beat, the film's words, and the curves everything moves on |
| `src/Reel.tsx` | The film: the layers, and the radar's line into the end card |
| `src/DeskLayer.tsx` | Home: it builds itself in shot 2 and is pushed into; it comes back round the calendar's rows and reflows on to the phone |
| `src/Chain.tsx` | What the answers share: the lens that pulls an answer back into its card, the lock's corners, a question's place, motion blur for flat pieces |
| `src/Devices.tsx` | The desktop window and the phone an answer is proved on, and the phone of shot 9 |
| `src/Questions.tsx` | Every word before the end card, on the film's own clock |
| `src/shots/` | One file a shot |
| `src/ui/kit.tsx`, `src/ui/Desk.tsx` | The app's interface rebuilt from `frontend/src`: its cards, and Home at desktop size |
| `src/ui/motion.tsx` | The app's elements as things that move: the counting number, placeholders, pops and landings |
| `src/three/` | The 3D stage (motion blur and depth of field by sampling), the coin, the phone's materials, and the mark |
| `src/Ground.tsx`, `src/Grain.tsx` | The dark ground and its one light; a faint grain over everything |
| `src/Sweep.tsx` | The radar's line as a change of scene (into the end card) |
| `src/Sound.tsx` | Every sound cue, each taking its frame from the animation it belongs to; the mix is the `LEVEL` table |
| `sound/make_sfx.py` | Makes every sound from arithmetic (numpy only) into `public/sfx/` |
| `src/fixtures/` | The figures: `film.json` (written by `scripts/fixtures.mjs` from the mock API's data) and `fall.json` (the day of shot 1) |
| `mock-api/` | A stand-in for the app's API with recorded market data and an example account |
| `blender/build_assets.py` | Builds the phone and the coin (`public/assets/`) |
| `scripts/` | `stills.mjs` renders chosen frames; `sheet.py` lays them on one sheet; `capture.mjs` photographs the app; `fixtures.mjs` writes the figures |
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
node scripts/fixtures.mjs                     # the film's figures, from the same data
```

- `record.mjs` refuses any address that names the portfolio, the account, the brief or
  the system page, and keeps only the three markets the app always follows: the full
  list of markets also names what the account holds. What it records
  (`mock-api/data/recorded/`) is not committed.
- `make_account.py` works the example account out with the app's own code from the
  holdings in `mock-api/example.json`. It opens the database read-only and never
  reads the stored portfolio, plan or account record.
- `capture.mjs` will not take a still unless the app it is pointed at is showing the
  example portfolio.
- Look at every still before using it: no loading placeholders, no fault, no figure
  that is not the example's.
- The film draws the app's pieces itself (`src/ui/`); of the stills it uses only Home at
  phone size, on the phone's screen. The desktop stills are the reference those pieces
  are checked against.

## Rules this film keeps

- **Every moving thing is a function of the frame.** No CSS transitions or keyframes, no
  timers, nothing random. The interface in `src/ui/` takes its animated values as props.
- **Nothing from an account.** Market figures come from the app's market addresses.
  Portfolio figures are the made-up example in `mock-api/example.json`, worked out by the
  app's own code, and what shows them says "Example portfolio". The app that shows an
  account is never photographed.
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
- **`zoom` enlarges an element's own placing too.** A piece of the app is placed by an
  outer element and enlarged by an inner one (`src/shots/Range.tsx`).
- **The mock API must keep its connections open.** Closing them stalled answers larger
  than 64 KB on this machine, and pages were photographed still loading.

## How the blur is made

`three/Stage.tsx` draws a blurred frame at 28 moments across the time the shutter is open
and averages them on a plain canvas, which is the one that is seen. A shot therefore gives
its camera, and anything that moves fast, as functions of the frame (`camera`, `move`),
so they can be asked for moments between two frames.
