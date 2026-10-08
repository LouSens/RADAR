# The RADAR film

A 30-second film, "The Calibration Laboratory".

- Story, timing and copy: [`docs/DEMO_STORYBOARD.md`](../docs/DEMO_STORYBOARD.md)
- How each shot is made: [`docs/DEMO_STAGING.md`](../docs/DEMO_STAGING.md)

**State: staged, not built.** The edit holds the nine shots at their lengths with their
copy over a plain ground. No assets exist yet.

## How it is made

| Part | Tool |
|---|---|
| Reusable 3D objects, each rendered alone on a transparent background | Blender |
| Composition, movement, depth, the cut, the copy, sound, the final render | Remotion |

No room is modelled in Blender and no shot is rendered there. An earlier pass did both;
it was the wrong architecture and was removed. It is in the branch history.

## Fixed points

- `src/shots.json` is the one place a shot's start and length are written.
- `src/timing.ts` holds the approved copy and the frames it is on screen.
- `src/Super.tsx` is the only typography: small, lower left, fades only.
- Rendered assets will live in `public/assets/<asset>/`.

```bash
npm --prefix demo-video run dev
```
