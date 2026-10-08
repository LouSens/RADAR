# RADAR film: staging for composited assets

Written 2026-10-08. This restages [`DEMO_STORYBOARD.md`](DEMO_STORYBOARD.md) for the
production method now in force. The story, the nine beats, their timing and the seven
lines of copy are unchanged. What changes is how each picture is made.

Where this file and the storyboard disagree about camera, room or hands, this file wins.
Nothing here is built yet.

## The method

- **Blender makes objects.** Each asset is modelled, lit and rendered alone, on a
  transparent background, and reused across shots.
- **Remotion makes the film.** It places the assets in depth, moves them, moves the
  view, cuts, sets the copy and carries the sound.
- **No room is modelled and no camera flies through one.**

## The world, built by composition

The film still has to read as one place. Six things hold it together, and every shot
uses all of them.

| Element | What it is | Made in |
|---|---|---|
| **The wall** | A soft, out-of-focus plaster plane with window light falling from the left | Remotion: a gradient with fine grain |
| **The bench** | A slate surface seen in perspective, running to a horizon about two-fifths up the frame | Blender: one slate texture, laid on a plane in Remotion's 3D stage |
| **The rail** | A blackened steel bar across the frame from which the mount and hopper hang | Blender still |
| **One light** | Everything is rendered under the same rig: a large soft source upper left, a weak fill, nothing else | Blender: one rig file shared by every asset |
| **One stage** | A single 3D stage with one virtual lens. Rendered assets are cards at real distances from it, so parallax and scale come from geometry, not from hand-set offsets | Remotion with `@remotion/three` |
| **Contact** | Every object that rests on something has its own shadow pass, laid on the surface under it | Blender shadow pass, composited in Remotion |

Depth of field is by distance: a card's blur follows how far it sits from the plane in
focus. The warming of the light in the last third is a grade applied in Remotion.

**One limit to accept.** A card can turn only by stepping through its turntable frames,
around one axis, under the light it was rendered in. The stage's view may therefore
slide, rise, fall and push in, but may not swing more than a few degrees around an
object. Every shot below is staged inside that limit.

## The shots

### Shot 1 · 0:00 to 0:04 · Confidence

| | |
|---|---|
| **Composition** | Close on the shelf of instruments, sliding past. Then the view opens out and down: the shelf rises and recedes, and the rail, the mount, the hopper and the top of the paddle board come into frame beneath it. |
| **Foreground** | One instrument passing very close, out of focus |
| **Midground** | The pendulum gauge, the etched glass and the clockwork on the shelf, sharp, each with a blank tag |
| **Background** | The wall. In the reveal: rail, mount, hopper, paddle board |
| **Blender assets** | Six instruments, tags, shelf plank, rail, mount with flag, hopper, paddle, board panel |
| **Remotion** | Stage, wall, depth blur, caption |
| **View movement** | A slow slide left to right for three seconds; then a pull back and a small drop, with the depth between layers stretching as it goes |
| **Into shot 2** | Cut on the gauge starting to lift from the shelf |
| **Angles** | Instruments three-quarter front at eye level, through the turntable. Shelf plank and board panel straight on |
| **Hands** | None. The gauge lifts on its own line of motion; the hand is implied |
| **Approach** | Cards on the stage. The reveal is a move of the virtual lens, not a scale tween |

### Shot 2 · 0:04 to 0:08 · The hero test

The first pipeline test.

| | |
|---|---|
| **Composition** | The mount hangs from the rail at centre. The gauge arrives and seats. Its needle swings to the right stop. The flag tips left. A ball drops from above, past the gauge, through the paddles, and lands on the sand to the right of the brass line. |
| **Foreground** | At the end: the crater and the ball, sharp |
| **Midground** | Mount, gauge, flag; then the paddle board as the view descends |
| **Background** | Wall; rail; at the end the flag, soft, still pointing left |
| **Blender assets** | Gauge with separate needle, mount with separate flag, steel ball (GLB), paddle, board panel, sand, crater, hopper edge |
| **Remotion** | Stage, ball motion from gravity, crater and a small lift of sand at the landing, depth blur, caption |
| **View movement** | Holds on the mount. Then travels straight down with the ball, layers passing at their own rates, and settles low over the sand |
| **Into shot 3** | Cut on the settled crater |
| **Angles** | Gauge and mount three-quarter front. Sand seen at a low angle |
| **Hands** | None |
| **Approach** | Cards for gauge, needle, mount, flag, board. The ball is real geometry so its fall, scale and reflection are true. Sand is a textured plane so the low angle is real |

### Shot 3 · 0:08 to 0:11.5 · The rhythm

| | |
|---|---|
| **Composition** | One continuous view of the rig. Four instruments take the mount in turn; the flag tips, a ball falls, a crater stays. The drops come faster each time. |
| **Foreground** | The sand, filling with craters and resting balls |
| **Midground** | Mount, the instrument of the moment, flag, paddle board |
| **Background** | The shelf, deeper in frame, refilling with tagged instruments |
| **Blender assets** | Etched glass, rail instrument, vane, clockwork, tags, plus everything from shot 2 |
| **Remotion** | Seeded timing of drops and landings; accumulation |
| **View movement** | One slow drift across the rig at constant speed. Every turntable asset steps a few degrees in step with it, so the drift reads as a move around the rig |
| **Into shot 4** | Hard cut, mid-beat |
| **Angles** | Turntable, across about fifteen degrees |
| **Hands** | None. Instruments travel between shelf and mount in stepped time |
| **Approach** | Same stage as shot 2, held wider |

### Shot 4 · 0:11.5 to 0:14 · Silence

| | |
|---|---|
| **Composition** | Sparse and still. The empty mount, flag upright. Two hands at rest on the rail. Far behind, the shelf of tagged instruments. |
| **Foreground** | The mount, slightly soft |
| **Midground** | The hands, sharp |
| **Background** | The shelf, soft; the wall |
| **Blender assets** | Mount with flag, rail, shelf plank, six instruments, tags |
| **Remotion** | Stage, caption, and nothing else |
| **View movement** | None. One tag swings and settles: the only motion in the shot |
| **Into shot 5** | The view begins to drop before the cut |
| **Angles** | Straight on |
| **Hands** | **Real, photographed.** A still of two hands resting on a bar |
| **Approach** | Three cards and a photograph. The rail in the photograph is replaced by the rendered rail so the hands sit on the film's object |

### Shot 5 · 0:14 to 0:16.5 · The turn

| | |
|---|---|
| **Composition** | The view drops. Shelf and mount leave by the top of the frame; the sand rises from the bottom and tilts towards us until we look almost straight down on it. The craters are thick near the brass line and thin towards the ends. |
| **Foreground** | The underside of the mount passing close and blurred as the view drops: the object that hands the frame from instruments to sand |
| **Midground** | The sand and its craters |
| **Background** | The wall, until the sand fills the frame |
| **Blender assets** | Sand, crater, resting ball, mount, brass line |
| **Remotion** | The same seeded crater field as shot 3 |
| **View movement** | A drop and a tilt: from level to nearly overhead |
| **Into shot 6** | The descent continues; cut along it |
| **Angles** | Sand from thirty degrees to overhead |
| **Hands** | None |
| **Approach** | The sand is a plane on the stage, so the tilt is real geometry. The cut is motivated by the view's own movement and by the mount passing: no wipe |

### Shot 6 · 0:16.5 to 0:19.5 · The second measurement

| | |
|---|---|
| **Composition** | Very low across the craters, light raking. The seismograph stands at the left. Its paper strip unrolls along the near edge of the bed, beside the craters. |
| **Foreground** | The paper strip and its trace |
| **Midground** | Crater rims in raking light |
| **Background** | The seismograph, soft; dark beyond |
| **Blender assets** | Sand and craters lit low, seismograph, paper strip, slate edge |
| **Remotion** | The trace, drawn from the film's own crater data so it agrees roughly and disagrees in one place; the unrolling |
| **View movement** | A slow track along the bed |
| **Into shot 7** | Cut on the strip coming to rest |
| **Angles** | Sand at a grazing angle, with a second texture lit from low. Seismograph three-quarter, low |
| **Hands** | None. The strip unrolls as if released |
| **Approach** | Sand plane, cards, one drawn line on a paper texture |

### Shot 7 · 0:19.5 to 0:25 · Many outcomes

| | |
|---|---|
| **Composition** | In three movements. A drawer of balls slides open and empties upward into the hopper. The view enters the mechanism and falls among the paddles as balls strike them. Then it draws back and up as thousands of balls heap into a ridge along the bed, thin at the ends, a few rolling off. |
| **Foreground** | Paddles and balls passing within a hand's width of the lens |
| **Midground** | The falling stream; then the ridge |
| **Background** | Board panel and glass; then the wall |
| **Blender assets** | Drawer, hopper, paddle (as geometry), steel ball (as geometry), board panel, sand, slate edge |
| **Remotion** | Thousands of instanced balls on seeded paths; paddles re-setting before each run |
| **View movement** | Follow the drawer; rise to the hopper; fall through the mechanism; pull back and up to the widest view of the film |
| **Into shot 8** | The last ball settles; the view starts down |
| **Angles** | Free: this is the one shot whose main elements are true geometry |
| **Hands** | None |
| **Approach** | Paddles and balls are real 3D objects on the stage, because the lens passes among them and cards would look flat. Both are simple shapes whose brass and steel hold up there. Reflections come from an image of the Blender light rig, so the metal matches the rendered assets |

### Shot 8 · 0:25 to 0:28 · One ball

| | |
|---|---|
| **Composition** | Bench height. Two brass markers press into the sand either side of the thick of the ridge; balls lie beyond both. In front, an open palm holding one steel ball. The fingers close. |
| **Foreground** | The hand |
| **Midground** | Markers and ridge, soft |
| **Background** | The wall, warm |
| **Blender assets** | Range marker, sand, the ridge as left by shot 7 |
| **Remotion** | Warm grade; a soft shadow from the hand onto the bed; caption |
| **View movement** | A slow push towards the hand |
| **Into shot 9** | Focus leaves the hand |
| **Angles** | Markers three-quarter front |
| **Hands** | **Real, filmed.** An open palm holding a real steel ball, closing. The ball is real too: a real ball in a real hand will always sit better than a rendered one composited onto skin |
| **Approach** | A filmed plate, cut out, placed in front of the stage. The plate is lit from the left and graded to the scene |

### Shot 9 · 0:28 to 0:30 · The name

| | |
|---|---|
| **Composition** | The closed hand, soft, upper left. Below it, on the front edge of the bed, a brass maker's plate comes into focus: RADAR. |
| **Foreground** | The maker's plate |
| **Midground** | The slate edge it is fixed to |
| **Background** | The hand; the ridge; the wall |
| **Blender assets** | Maker's plate, slate edge |
| **Remotion** | The focus pull; a slow light across the engraving; the line under it |
| **View movement** | A very slight push |
| **End** | Hold, then cut to black |
| **Angles** | Plate straight on and three degrees off; a short sequence of a light crossing the engraving |
| **Hands** | The last frame of shot 8's plate, held |
| **Approach** | Two cards and the held plate |

## Assets this staging needs

Set pieces were missing from the first inventory. They are single objects, not a room.

| Asset | Format | Variants | Shots |
|---|---|---|---|
| Steel ball | Geometry (GLB), plus one still | | All |
| Pendulum gauge | Turntable, 72 frames; needle as its own layer | | 1, 2, 3, 4 |
| Mount | Still; flag as its own layer | Front, and from below for shot 5 | 1 to 5 |
| RADAR maker's plate | Still | Straight, three degrees off; light-sweep sequence | 9 |
| Sand | Texture for a plane | Lit from high; lit from low | 2 to 8 |
| Crater | Texture with transparency | Lit from high; lit from low | 2 to 8 |
| Brass paddle | Geometry (GLB) | | 1, 2, 3, 7 |
| Board panel with glass | Still | | 1, 2, 3, 7 |
| Rail | Still | | 1 to 4 |
| Shelf plank | Still | | 1, 3, 4 |
| Slate edge | Still | | 6, 8, 9 |
| Hopper | Still | From the side; from below | 1, 2, 7 |
| Etched glass, rail instrument, vane, clockwork | Turntable; vane and wheels as their own layers | | 1, 3, 4 |
| Seismograph | Turntable; drum and stylus as their own layers | | 1, 6 |
| Tag | Still | Blank; pencilled | 1, 3, 4 |
| Paper strip | Texture | | 6 |
| Range marker | Still | | 8 |
| Drawer | Still | Closed; open and full | 7 |
| Light rig image | Environment image | | Every shot with geometry |

A settled heap rendered in Blender is not needed: shot 7 leaves the real one on the stage.

## Hand plates to shoot

| Plate | What | How |
|---|---|---|
| Shot 4 | Two hands at rest on a bar, still | A photograph. Camera level with the hands, straight on |
| Shot 8 | An open palm holding a steel ball; the fingers close | Video, three seconds, locked off. Camera slightly above the palm |

Both: soft light from the left and nothing from the right; a plain mid-grey background a
metre behind; undyed sleeves rolled to the elbow; no watch or rings; a real steel ball of
about a centimetre. Shoot wider than needed and at the highest resolution available.

Until they exist, a plain grey card stands in at the hand's position and size. No
composition is designed around a rendered hand.

## The first test: shot 2

Built from four assets: the steel ball, the pendulum gauge, the mount with its flag, and
the maker's plate (rendered now, used in shot 9). Shot 2 also needs sand, a crater and a
paddle; for the test these may be rough.

It passes only if it looks like one photographed place. It fails if it reads as pictures
sliding over a background, a slideshow, a template, or a 3D demo. If it fails, the
composition is reworked before any further asset is made.

## Open risks

- **Blur by depth** on rendered cards is assumed to be a filter per layer. Whether that
  holds at render speed and quality has to be checked in the shot 2 test.
- **Turntable steps.** Seventy-two frames is five degrees a step. The slow drift in shot
  3 may show stepping; if so, that asset needs a finer sequence across the angles used.
- **Shot 7 at close range.** Brass paddles as real-time geometry will be the least rich
  metal in the film at the moment they are closest to the lens. If they fall short, the
  fall through the mechanism is rendered in Blender as one element and composited.
- **The hand plates** decide whether shots 4 and 8 work. They cannot be judged until
  they are shot.
