# The RADAR film

A 30-second film, "The Calibration Laboratory". The creative and shot specification is
[`docs/DEMO_STORYBOARD.md`](../docs/DEMO_STORYBOARD.md): read it first.

**State: blocked-out animatic.** Placeholder geometry, flat materials, stand-in hands.
It exists to prove the room, the nine cameras and the timing. Nothing here is the final
look, and there is no sound yet.

## How it is made

| Part | Tool | Where |
|---|---|---|
| The room, objects, motion, cameras, light | Blender 5 | `blender/blockout.py` |
| Shot timing, shared by both | one file | `src/shots.json` |
| The edit, the copy, sound, the final render | Remotion 4 | `src/` |

Blender renders one picture-only plate per shot. Remotion lays the plates end to end,
sets the copy over them and will carry the sound.

## Run it

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b -P demo-video/blender/blockout.py -- --render
```

That builds the scene from nothing, saves `blender/lab_blockout.blend` and writes
`public/plates/shot1.mp4` to `shot9.mp4` (about two minutes). Then:

```bash
npm --prefix demo-video run dev
```

Useful variations:

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b -P demo-video/blender/blockout.py -- --render --stills
```

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b -P demo-video/blender/blockout.py -- --render --shots 7
```

`--stills` writes three frames per shot to `blender/stills/`, and
`python blender/contact_sheet.py` joins them into one sheet. `--shots 2,7` renders only
those plates.

## Decisions later work depends on

1. **`src/shots.json` is the only place a shot's start and length are written.**
   `blockout.py` reads it for frame ranges and camera markers; `src/timing.ts` reads it
   for the edit. Change a length there and both follow. Shots are cut, never dissolved,
   so no shot needs handles.
2. **One Blender scene, one continuous timeline of 900 frames.** A shot is a frame range
   and a camera bound to a timeline marker, not a separate file. Objects are in the room
   from frame 0 and carry their state forward: the craters made in shot 3 are the ones
   seen in shots 5 and 6.
3. **The scene is built by script, from nothing, every time.** No hand edits to the
   `.blend`: it is generated, and ignored by git, as are the stills and the plates. When
   detailed assets arrive they are appended by the script from asset files, so the
   blocking stays reproducible.
4. **Everything random is seeded.** Where balls land, which way the flag tips and how
   the paddles re-set come from one seeded generator, so a re-render matches the last.
5. **Motion is keyed, not simulated live.** Ball falls are computed from gravity and
   written as keys. Any real physics added later must be baked to keys or a cache before
   rendering, for the same reason.
6. **Plates are picture only**, 30 frames a second, named `shotN.mp4`. The blockout
   renders at 960 × 540 with the Workbench engine. Final plates should be 1920 × 1080
   image sequences or a visually lossless codec, at the same names and frame counts, so
   the edit does not change.
7. **Copy is never rendered into a plate.** It is set in Remotion (`src/Super.tsx`,
   wording and frames in `src/timing.ts`) so it stays sharp and editable. The one
   exception is in the world: RADAR engraved on the maker's plate.
8. **Sound belongs to the film's timeline, not to a shot**, because room tone and the
   one sustained note run across cuts.
9. **Blender 5 keeps animation curves in layered actions.** The scripted preference for
   key interpolation is ignored there, so `blockout.py` sets each key's curve itself
   (`shape`). Without it, objects meant to appear at a frame fade in from frame 0.

## Where the blockout departs from the storyboard

- **The tower is as wide as the bed**, standing behind it, with the paddle cascade as a
  glass-fronted board facing the room. A narrow tower at the head of the bed could not
  spread outcomes along the bed's length, and stood in the way of the overhead shot.
- **The shelf is at eye level**, above the board, so the instruments are seen past the
  empty mount in shot 4.
- **The maker's plate is on the front of the bed**, not the tower's base. From the last
  camera position the heap of balls hid the tower's base; on the bed the plate sits just
  under the closing hand and the last shot is a true focus pull.
- **The hands rest on the board's top rail** in shot 4, either side of the mount.

## Not done

Detailed models, materials, lighting and the warming of the light; sand that deforms;
real or rigged hands; ten thousand balls (the blockout uses 3,500, in five joined
meshes); the seismograph's trace; sound; the final render.
