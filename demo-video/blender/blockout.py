"""The calibration laboratory, blocked out: one room, nine cameras, 900 frames.

Builds the whole scene from nothing, saves it beside this file, and (with --render)
renders one low-resolution plate per shot for the Remotion edit. Placeholder geometry
only: this proves layout, timing and camera, not the look.

    blender -b -P demo-video/blender/blockout.py -- --render
    blender -b -P demo-video/blender/blockout.py -- --render --shots 2,7 --stills

The shot list and frame ranges come from shots.json, which the Remotion project reads
too, so the two can never disagree. Everything random is seeded.
"""

import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
SHOTS = json.loads((HERE.parent / "src" / "shots.json").read_text(encoding="utf-8"))
FPS = SHOTS["fps"]
RANGE = {shot["id"]: (shot["from"], shot["from"] + shot["frames"] - 1) for shot in SHOTS["shots"]}
ARGS = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
RNG = random.Random(7)

# ---------------------------------------------------------------- the room, in metres
SAND_TOP = 0.95
BALL = 0.012
REST = SAND_TOP + BALL
DROP_Y = 0.2  # the plane the balls fall in, just in front of the paddle board
HOPPER = Vector((0.0, DROP_Y, 2.5))
MOUNT = Vector((0.0, 0.34, 1.9))
SHELF_Y, SHELF_Z = 1.82, 1.95
SHELF_X = [-1.5, -0.9, -0.3, 0.3, 0.9, 1.5]
BOARD = (1.1, 1.7)  # the paddle cascade, bottom and top
BED_HALF = 1.2
GRAVITY = 9.81


# ---------------------------------------------------------------- small helpers
def material(name, colour, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*colour, alpha)
    return mat


KIND = "BEZIER"


def interpolation(kind):
    """The curve every key inserted from now on gets."""
    global KIND
    KIND = kind


def curves(block):
    """Every animation curve of an object or its data. Blender 5 keeps them in layered
    actions, one bag of curves per slot."""
    data = block.animation_data
    if data is None or data.action is None:
        return []
    return [
        curve
        for layer in data.action.layers
        for strip in layer.strips
        for bag in strip.channelbags
        for curve in bag.fcurves
    ]


def shape(block, frame):
    """Give the keys just inserted at `frame` the curve that was asked for."""
    for curve in curves(block):
        for point in curve.keyframe_points:
            if point.co.x == frame:
                point.interpolation = KIND


def box(name, size, location, mat, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name, obj.scale = name, size
    obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def cylinder(name, radius, depth, location, mat, rotation=(0, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, location=location, rotation=rotation, vertices=vertices
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def sphere(name, location, mat, radius=BALL):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, location=location, segments=12, ring_count=6
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def key(obj, frame, location=None, rotation=None, scale=None):
    if location is not None:
        obj.location = location
        obj.keyframe_insert("location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = rotation
        obj.keyframe_insert("rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = (scale, scale, scale) if isinstance(scale, (int, float)) else scale
        obj.keyframe_insert("scale", frame=frame)
    shape(obj, frame)


def appear(obj, frame):
    """Nothing before `frame`, there from then on."""
    interpolation("CONSTANT")
    size = tuple(obj.scale)
    key(obj, 0, scale=0.0)
    key(obj, frame, scale=size)


def path(obj, keys):
    """Straight moves between (frame, location) pairs; two keys a frame apart jump."""
    interpolation("LINEAR")
    for frame, location in keys:
        key(obj, frame, location=location)


def fall(ball, start, land, rise=0.0):
    """A ball let go at `start` from the hopper, pushed sideways only while it is in the
    paddle cascade, and at rest where it lands. Returns the landing frame."""
    interpolation("LINEAR")
    target = Vector((land[0], land[1], REST + rise))
    height = HOPPER.z - target.z
    frames = math.ceil(math.sqrt(2 * height / GRAVITY) * FPS)
    key(ball, 0, location=HOPPER)
    key(ball, start, location=HOPPER)
    for step in range(1, frames + 1):
        t = step / FPS
        z = max(HOPPER.z - 0.5 * GRAVITY * t * t, target.z)
        through = min(max((BOARD[1] - z) / (BOARD[1] - BOARD[0]), 0.0), 1.0)
        wobble = 0.02 * math.sin(through * 19 + land[0] * 40) * (1 - through)
        x = target.x * through + wobble
        y = HOPPER.y + (target.y - HOPPER.y) * through
        key(ball, start + step, location=(x, y, z))
    return start + frames


def landing(spread=0.33):
    """Where a ball comes to rest on the bed: crowded near the line, thin far out."""
    x = max(min(RNG.gauss(0.0, spread), BED_HALF - 0.05), -BED_HALF + 0.05)
    y = max(min(RNG.gauss(0.06, 0.09), 0.26), -0.26)
    return x, y


# ---------------------------------------------------------------- start from nothing
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 0, SHOTS["frames"] - 1

WALL = material("plaster", (0.78, 0.79, 0.8))
FLOOR = material("floor", (0.33, 0.3, 0.27))
WINDOW = material("window", (0.93, 0.96, 1.0))
SLATE = material("slate", (0.2, 0.21, 0.23))
SAND = material("sand", (0.86, 0.82, 0.72))
BRASS = material("brass", (0.72, 0.56, 0.27))
STEEL = material("blackened steel", (0.09, 0.09, 0.1))
BRIGHT = material("ball steel", (0.75, 0.77, 0.8))
WALNUT = material("walnut", (0.3, 0.2, 0.13))
GLASS = material("glass", (0.75, 0.9, 0.88), 0.18)
PAPER = material("paper", (0.9, 0.86, 0.74))
CRATER = material("crater shadow", (0.62, 0.58, 0.49))
SKIN = material("hand proxy", (0.78, 0.62, 0.52))
LINEN = material("linen", (0.82, 0.79, 0.72))

# ---------------------------------------------------------------- the room
box("floor", (6.4, 4.4, 0.1), (0, 0, -0.05), FLOOR)
box("wall back", (6.4, 0.1, 3.2), (0, 2.05, 1.6), WALL)
box("wall left", (0.1, 4.4, 3.2), (-3.05, 0, 1.6), WALL)
box("wall right", (0.1, 4.4, 3.2), (3.05, 0, 1.6), WALL)
box("north window", (0.02, 1.6, 1.9), (-2.99, -0.2, 1.75), WINDOW)

box("bench", (2.9, 0.95, 0.9), (0, 0, 0.45), WALNUT)
box("slate rim", (2.56, 0.76, 0.06), (0, 0, 0.92), SLATE)
box("sand", (2.4, 0.6, 0.02), (0, 0, SAND_TOP - 0.01), SAND)
box("brass line", (0.004, 0.6, 0.002), (0, 0, SAND_TOP + 0.001), BRASS)

# The tower: a frame behind the bed carrying the hopper, the mount, and a glass-fronted
# board of paddles as wide as the bed. All of it is here from the first frame.
for side in (-1.25, 1.25):
    box(f"tower post {side}", (0.05, 0.05, 1.9), (side, 0.45, 1.85), STEEL)
box("tower top beam", (2.6, 0.06, 0.06), (0, 0.45, 2.78), STEEL)
box("tower mount beam", (2.6, 0.04, 0.04), (0, 0.45, 1.78), STEEL)
box("tower base", (2.6, 0.3, 0.14), (0, 0.5, 1.02), STEEL)
bpy.ops.mesh.primitive_cone_add(
    radius1=0.2, radius2=0.03, depth=0.3, location=(0, DROP_Y, 2.66), rotation=(math.pi, 0, 0)
)
bpy.context.object.name = "hopper"
bpy.context.object.data.materials.append(BRASS)
box("mount cradle", (0.22, 0.08, 0.05), (MOUNT.x, MOUNT.y, MOUNT.z - 0.09), BRASS)
box("mount arm", (0.03, 0.14, 0.03), (0, 0.41, 1.8), STEEL)
box("board back", (2.4, 0.015, BOARD[1] - BOARD[0] + 0.1), (0, 0.25, sum(BOARD) / 2), STEEL)
box("board glass", (2.4, 0.006, BOARD[1] - BOARD[0] + 0.1), (0, 0.155, sum(BOARD) / 2), GLASS)

flag = box("flag", (0.012, 0.004, 0.07), (0.16, 0.3, 2.0), BRASS)
PLATE = Vector((0.05, -0.384, 0.918))
plate = box("maker's plate", (0.16, 0.006, 0.04), PLATE, BRASS)
bpy.ops.object.text_add(
    location=(PLATE.x - 0.052, PLATE.y - 0.004, PLATE.z - 0.011), rotation=(math.pi / 2, 0, 0)
)
name = bpy.context.object
name.name, name.data.body, name.data.size, name.data.extrude = "engraving", "RADAR", 0.028, 0.0006
name.data.materials.append(STEEL)

paddles = []
for row in range(4):
    for column in range(10):
        x = -1.08 + column * 0.24 + (0.12 if row % 2 else 0.0)
        paddles.append(
            box(
                f"paddle {row}.{column}",
                (0.012, 0.03, 0.08),
                (x, DROP_Y, BOARD[1] - 0.09 - row * 0.14),
                BRASS,
            )
        )

# The shelf and its six instruments. Rough stand-ins, one silhouette each.
box("shelf", (4.0, 0.3, 0.04), (0, SHELF_Y, SHELF_Z - 0.02), WALNUT)


def instrument(index, label):
    root = bpy.data.objects.new(label, None)
    bpy.context.collection.objects.link(root)
    root.location = (SHELF_X[index], SHELF_Y, SHELF_Z)
    if label == "pendulum gauge":
        cylinder("gauge base", 0.07, 0.03, (0, 0, 0.015), BRASS).parent = root
        cylinder("gauge dome", 0.06, 0.13, (0, 0, 0.095), GLASS).parent = root
        box("gauge needle", (0.006, 0.006, 0.1), (0, 0, 0.09), STEEL, root)
    elif label == "etched glass":
        box("glass frame", (0.2, 0.03, 0.02), (0, 0, 0.01), BRASS, root)
        box("glass plate", (0.18, 0.012, 0.2), (0, 0, 0.12), GLASS, root)
    elif label == "rail":
        box("rail post", (0.02, 0.02, 0.16), (-0.07, 0, 0.08), BRASS, root)
        box("rail channel", (0.2, 0.03, 0.015), (0.02, 0, 0.15), BRASS, root).rotation_euler = (
            0,
            0.35,
            0,
        )
    elif label == "vane":
        cylinder("vane ring", 0.09, 0.02, (0, 0, 0.02), BRASS).parent = root
        box("vane post", (0.012, 0.012, 0.16), (0, 0, 0.1), STEEL, root)
        box("vane blade", (0.14, 0.006, 0.05), (0, 0, 0.18), BRASS, root)
    elif label == "clockwork":
        for step, radius in enumerate((0.08, 0.055, 0.035)):
            cylinder(
                f"wheel {step}", radius, 0.025, (0, 0, 0.02 + step * 0.045), BRASS
            ).parent = root
    else:  # the seismograph: plain, and last on the shelf
        box("seismograph base", (0.22, 0.12, 0.02), (0, 0, 0.01), WALNUT, root)
        cylinder(
            "drum", 0.045, 0.14, (0, 0, 0.07), PAPER, rotation=(0, math.pi / 2, 0)
        ).parent = root
        box("stylus arm", (0.006, 0.09, 0.006), (0.03, -0.04, 0.12), STEEL, root)
    tag = box(f"tag {index}", (0.05, 0.002, 0.03), (0.09, -0.14, -0.03), PAPER, root)
    return root, tag


INSTRUMENTS = [
    instrument(i, label)
    for i, label in enumerate(
        ["pendulum gauge", "etched glass", "rail", "vane", "clockwork", "seismograph"]
    )
]

# The drawers of past days: three cabinets on the right wall, one drawer that works.
for index, y in enumerate((-1.0, 0.0, 1.0)):
    box(f"cabinet {index}", (0.34, 0.8, 1.4), (2.83, y, 1.0), WALNUT)
    box(f"cabinet plate {index}", (0.004, 0.2, 0.04), (2.655, y, 1.62), BRASS)
drawer = box("drawer", (0.3, 0.24, 0.09), (2.72, 0.0, 1.2), WALNUT)
for index in range(14):
    sphere(
        f"drawer ball {index}", (RNG.uniform(-0.3, 0.3), RNG.uniform(-0.3, 0.3), 0.75), BRIGHT, 0.14
    ).parent = drawer


# Hands: crude stand-ins, a forearm and a palm with one slab for the fingers.
def hand(label):
    palm = box(f"{label} palm", (0.09, 0.11, 0.03), (0, -0.6, 1.0), SKIN)
    box(f"{label} forearm", (0.8, 2.6, 1.6), (0, -1.75, 0.1), LINEN, palm)
    fingers = box(f"{label} fingers", (1.0, 0.75, 0.8), (0, 0.85, 0.0), SKIN, palm)
    return palm, fingers


RIGHT, RIGHT_FINGERS = hand("right")
LEFT, LEFT_FINGERS = hand("left")

# ---------------------------------------------------------------- shot 1 and 2
S = RANGE
gauge, gauge_tag = INSTRUMENTS[0]
shelf_spot = lambda i: Vector((SHELF_X[i], SHELF_Y, SHELF_Z))  # noqa: E731
path(
    gauge,
    [
        (0, shelf_spot(0)),
        (S["shot2"][0] - 20, shelf_spot(0)),
        (S["shot2"][0] - 1, shelf_spot(0) + Vector((0, -0.1, 0.12))),
        (S["shot2"][0], Vector((-0.45, 0.1, 2.05))),
        (S["shot2"][0] + 24, MOUNT),
        (S["shot2"][1], MOUNT),
        (S["shot3"][0], shelf_spot(0)),
    ],
)
appear(gauge_tag, S["shot3"][0])

interpolation("BEZIER")
tip = S["shot2"][0] + 44
key(flag, 0, rotation=(0, 0, 0))
key(flag, tip - 6, rotation=(0, 0, 0))
key(flag, tip, rotation=(0, -0.7, 0))  # the call: left
key(flag, S["shot2"][1], rotation=(0, -0.7, 0))

hero = sphere("hero ball", HOPPER, BRIGHT)
hero_lands = fall(hero, S["shot2"][0] + 56, (0.22, 0.05))  # and it lands right


def crater(index, spot, frame):
    disc = cylinder(
        f"crater {index}", 0.022, 0.004, (spot[0], spot[1], SAND_TOP + 0.002), CRATER, vertices=16
    )
    appear(disc, frame)


crater(0, (0.22, 0.05), hero_lands)

# ---------------------------------------------------------------- shot 3: the rhythm
first, last = S["shot3"]
swaps = [first, first + 27, first + 48, first + 63]
gaps = [0.9, 0.7, 0.5, 0.35, 0.25, 0.25, 0.25, 0.2, 0.2, 0.2, 0.15, 0.15, 0.15, 0.15]
drops, at = [], first + 8.0
for gap in gaps:
    drops.append(round(at))
    at += gap * FPS
drops = [frame for frame in drops if frame < last - 16]

for slot, (root, tag) in enumerate(INSTRUMENTS[1:5], start=1):
    start = swaps[slot - 1]
    end = swaps[slot] if slot < 4 else last + 1
    path(
        root,
        [
            (0, shelf_spot(slot)),
            (start - 1, shelf_spot(slot)),
            (start, MOUNT),
            (end - 1, MOUNT),
            (end, shelf_spot(slot)),
        ],
    )
    appear(tag, end)

interpolation("BEZIER")
count = 1
for frame in drops:
    call = RNG.choice((-0.7, 0.7))
    key(flag, frame - 5, rotation=(0, 0, 0))
    key(flag, frame - 1, rotation=(0, call, 0))
    spot = landing()
    ball = sphere(f"test ball {count}", HOPPER, BRIGHT)
    crater(count, spot, fall(ball, frame, spot))
    count += 1
interpolation("BEZIER")
key(flag, last, rotation=(0, 0, 0))

# Stepped time: far more tests than the eye follows. Their marks gather by the cut.
for extra in range(130):
    spot = landing()
    frame = round(first + 40 + (last - first - 42) * (extra / 130) ** 0.6)
    crater(count, spot, frame)
    appear(sphere(f"rest ball {count}", (spot[0], spot[1], REST), BRIGHT), frame)
    count += 1
for far in (-1.1, -0.98, 1.02, 1.12):  # the few that lie a long way out
    crater(count, (far, 0.05), last - 6)
    appear(sphere(f"rest ball {count}", (far, 0.05, REST), BRIGHT), last - 6)
    count += 1

# ---------------------------------------------------------------- shot 6: the second measurement
seismograph, seismograph_tag = INSTRUMENTS[5]
bench_spot = Vector((-1.32, -0.2, 0.96))
path(
    seismograph,
    [(0, shelf_spot(5)), (S["shot6"][0] + 14, shelf_spot(5)), (S["shot6"][0] + 15, bench_spot)],
)
appear(seismograph_tag, S["shot6"][0] + 15)
strip = box("paper strip", (2.3, 0.07, 0.002), (0, -0.345, 0.952), PAPER)
interpolation("LINEAR")
key(strip, 0, location=(-1.15, -0.345, 0.952), scale=(0.0, 0.07, 0.002))
key(strip, S["shot6"][0] + 34, location=(-1.15, -0.345, 0.952), scale=(0.0, 0.07, 0.002))
key(strip, S["shot6"][0] + 72, location=(0, -0.345, 0.952), scale=(2.3, 0.07, 0.002))

# ---------------------------------------------------------------- shot 7: many outcomes
first, last = S["shot7"]
pour, release = first + 50, first + 62
path(
    drawer,
    [
        (0, (2.72, 0, 1.2)),
        (first + 14, (2.72, 0, 1.2)),
        (first + 28, (2.45, 0, 1.2)),
        (first + 38, (2.45, 0, 1.2)),
        (first + 50, (0.12, 0.05, 2.9)),
        (first + 60, (0.12, 0.05, 2.9)),
        (first + 70, (1.6, -0.6, 1.5)),
    ],
)

interpolation("BEZIER")
for paddle in paddles:  # re-set before each run: the pushes are never the same twice
    key(paddle, release - 4, rotation=(0, 0, 0))
    for frame in range(release, last, 7):
        key(paddle, frame + RNG.randint(0, 5), rotation=(0, RNG.uniform(-0.6, 0.6), 0))


def ridge(x):
    """How high the heap stands at `x` once everything has landed."""
    return 0.11 * math.exp(-(x * x) / (2 * 0.3 * 0.3))


for index in range(70):
    spot = landing(0.3)
    start = release + round(index * 1.1)
    ball = sphere(f"outcome {index}", HOPPER, BRIGHT)
    fall(ball, start, spot, rise=ridge(spot[0]) * min((start - release) / 70, 1.0))

for index, side in enumerate((-1, 1, 1, -1, 1, -1)):  # the ones that leave the bed
    start = release + 18 + index * 11
    ball = sphere(f"leaver {index}", HOPPER, BRIGHT)
    landed = fall(ball, start, (side * (BED_HALF - 0.06), 0.0))
    interpolation("LINEAR")
    key(ball, landed + 9, location=(side * (BED_HALF + 0.13), -0.05, REST))
    key(ball, landed + 22, location=(side * (BED_HALF + 0.3), -0.1, BALL))
    key(ball, landed + 40, location=(side * (BED_HALF + 0.75 + index * 0.1), -0.35, BALL))

# The mass of them: five sheets of several hundred, each arriving as rain. Joined into
# five meshes so that thousands of balls cost almost nothing to animate.
cells = {}
PER_SHEET = 700
for sheet in range(5):
    mesh = bpy.data.meshes.new(f"sheet {sheet}")
    build = bmesh.new()
    for _ in range(PER_SHEET):
        x, y = landing(0.3)
        cell = (round(x / 0.024), round(y / 0.024))
        cells[cell] = cells.get(cell, 0) + 1
        z = REST + min(cells[cell] * 0.011, ridge(x) + 0.02)
        made = bmesh.ops.create_icosphere(build, subdivisions=1, radius=BALL)
        bmesh.ops.translate(build, verts=made["verts"], vec=(x, y, z))
    build.to_mesh(mesh)
    build.free()
    obj = bpy.data.objects.new(f"outcomes sheet {sheet}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(BRIGHT)
    arrive = release + 22 + sheet * 16
    interpolation("LINEAR")
    key(obj, 0, location=(0, 0, 0), scale=0.0)
    key(obj, arrive - 1, location=(0, 0, 0), scale=0.0)
    for step in range(0, 13):
        t = (12 - step) / FPS
        key(obj, arrive + step, location=(0, 0, 0.5 * GRAVITY * t * t), scale=1.0)

# ---------------------------------------------------------------- shot 8: one ball
first, last = S["shot8"]
markers = [
    box(f"marker {side}", (0.006, 0.5, 0.09), (side * 0.47, 0, 1.2), BRASS) for side in (-1, 1)
]
for marker, press in zip(markers, (first + 10, first + 22), strict=True):
    x = marker.location.x
    path(
        marker,
        [
            (0, (x, -0.9, 0.5)),
            (press - 9, (x, -0.9, 0.5)),
            (press - 8, (x, 0, 1.16)),
            (press, (x, 0, SAND_TOP + 0.03)),
        ],
    )
PALM = Vector((-0.28, -0.42, 1.06))
chosen = sphere("the one ball", (0.04, 0.02, REST + 0.12), BRIGHT)
appear(chosen, first + 30)
path(
    chosen,
    [
        (first + 30, (0.04, 0.02, REST + 0.12)),
        (first + 34, (0.04, 0.02, REST + 0.12)),
        (first + 48, PALM + Vector((0, 0.02, 0.03))),
        (S["shot9"][1], PALM + Vector((0, 0.02, 0.03))),
    ],
)

# ---------------------------------------------------------------- the hands, through the film
REST_R, REST_L = Vector((0.42, 0.33, 1.82)), Vector((-0.42, 0.33, 1.82))
path(
    RIGHT,
    [
        (0, (-1.5, 1.2, 1.3)),
        (S["shot1"][1] - 22, (-1.5, 1.2, 1.3)),
        (S["shot1"][1], shelf_spot(0) + Vector((0, -0.24, 0.16))),
        (S["shot2"][0], Vector((-0.45, -0.12, 2.09))),
        (S["shot2"][0] + 24, MOUNT + Vector((0, -0.24, 0.05))),
        (S["shot2"][0] + 36, Vector((0.7, -0.5, 1.6))),
        (S["shot3"][0], MOUNT + Vector((0.1, -0.24, 0.05))),
        (S["shot3"][0] + 14, Vector((0.6, 0.5, 1.7))),
        (S["shot3"][0] + 27, MOUNT + Vector((0.1, -0.24, 0.05))),
        (S["shot3"][0] + 38, Vector((0.6, 0.5, 1.7))),
        (S["shot3"][0] + 48, MOUNT + Vector((0.1, -0.24, 0.05))),
        (S["shot3"][0] + 56, Vector((0.6, 0.5, 1.7))),
        (S["shot3"][0] + 63, MOUNT + Vector((0.1, -0.24, 0.05))),
        (S["shot3"][1], Vector((0.6, 0.5, 1.7))),
        (S["shot4"][0], REST_R),
        (S["shot5"][0] + 30, REST_R),
        (S["shot6"][0] - 1, Vector((1.2, -0.5, 1.1))),
        (S["shot6"][0] + 20, Vector((-1.3, -0.45, 1.02))),
        (S["shot6"][0] + 34, Vector((-1.1, -0.4, 1.0))),
        (S["shot6"][0] + 72, Vector((1.0, -0.4, 1.0))),
        (S["shot6"][1], Vector((1.5, -0.5, 1.15))),
        (S["shot7"][0] + 14, Vector((2.5, -0.2, 1.24))),
        (S["shot7"][0] + 28, Vector((2.25, -0.2, 1.24))),
        (S["shot7"][0] + 50, Vector((0.12, -0.2, 2.94))),
        (S["shot7"][0] + 60, Vector((0.12, -0.2, 2.94))),
        (S["shot7"][0] + 70, Vector((1.6, -0.8, 1.5))),
        (S["shot8"][0] + 12, Vector((0.47, -0.3, 1.08))),
        (S["shot8"][0] + 22, Vector((0.47, -0.3, 1.02))),
        (S["shot8"][0] + 32, Vector((0.04, -0.2, 1.1))),
        (S["shot8"][0] + 48, PALM),
        (S["shot9"][1], PALM),
    ],
)
path(
    LEFT,
    [
        (0, (-2.0, -1.2, 1.0)),
        (S["shot4"][0] - 1, (-2.0, -1.2, 1.0)),
        (S["shot4"][0], REST_L),
        (S["shot5"][0] + 30, REST_L),
        (S["shot6"][0] - 1, Vector((-1.7, -0.6, 1.0))),
        (S["shot7"][0], Vector((-1.7, -0.6, 1.0))),
        (S["shot8"][0], Vector((-0.47, -0.3, 1.16))),
        (S["shot8"][0] + 10, Vector((-0.47, -0.3, 1.02))),
        (S["shot8"][0] + 30, Vector((-0.9, -0.5, 1.0))),
    ],
)
interpolation("BEZIER")
key(RIGHT_FINGERS, S["shot8"][0] + 60, rotation=(0, 0, 0))
key(RIGHT_FINGERS, S["shot8"][0] + 78, rotation=(-2.1, 0, 0))  # the hand closes


# ---------------------------------------------------------------- nine cameras
def camera(shot, keys, stop=2.8):
    """One camera for one shot. Each key is (offset, position, look-at, lens in mm)."""
    start = S[shot][0]
    data = bpy.data.cameras.new(f"{shot} camera")
    data.clip_start, data.sensor_width = 0.02, 36
    data.dof.use_dof = True
    # Wide and travelling shots stay sharp; only the close ones have thin focus.
    data.dof.aperture_fstop = {"shot3": 11, "shot5": 11, "shot7": 11, "shot4": 5.6, "shot6": 8}.get(
        shot, stop
    )
    cam = bpy.data.objects.new(f"{shot} camera", data)
    target = bpy.data.objects.new(f"{shot} look-at", None)
    for obj in (cam, target):
        bpy.context.collection.objects.link(obj)
    aim = cam.constraints.new("TRACK_TO")
    aim.target, aim.track_axis, aim.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    data.dof.focus_object = target
    interpolation("BEZIER")
    for offset, position, look, lens in keys:
        key(cam, start + offset, location=position)
        key(target, start + offset, location=look)
        data.lens = lens
        data.keyframe_insert("lens", frame=start + offset)
        shape(data, start + offset)
    marker = scene.timeline_markers.new(shot, frame=start)
    marker.camera = cam
    return cam


def orbit(degrees, radius=2.3, height=1.55):
    """A point on a circle around the tower."""
    return (
        radius * math.cos(math.radians(degrees)),
        radius * math.sin(math.radians(degrees)),
        height,
    )


camera(
    "shot1",
    [
        (0, (-1.62, 1.28, 2.06), (-1.5, 1.82, 2.03), 85),
        (80, (1.05, 1.4, 2.06), (1.2, 1.82, 2.03), 85),
        (119, (2.1, -2.3, 1.9), (0.0, 0.3, 1.75), 28),
    ],
)
camera(
    "shot2",
    [
        (0, (0.55, -0.75, 2.02), (0.0, 0.3, 1.94), 50),
        (56, (0.5, -0.7, 2.0), (0.0, 0.25, 1.95), 50),
        (hero_lands - S["shot2"][0], (0.5, -0.62, 1.12), (0.2, 0.08, 0.98), 50),
        (119, (0.46, -0.5, 1.07), (0.2, 0.08, 0.97), 60),
    ],
)
camera(
    "shot3",
    [
        (0, orbit(-118), (0.0, 0.25, 1.5), 35),
        (52, orbit(-93), (0.0, 0.25, 1.45), 35),
        (104, orbit(-68), (0.0, 0.25, 1.4), 35),
    ],
)
camera(
    "shot4",
    [
        (0, (0.2, -0.7, 1.98), (-0.05, 1.82, 1.9), 35),
        (74, (0.2, -0.7, 1.98), (-0.05, 1.82, 1.9), 35),
    ],
)
camera(
    "shot5",
    [
        (0, (0.2, -0.7, 1.98), (-0.05, 1.82, 1.9), 35),
        (40, (0.12, -0.5, 2.3), (0.0, 0.1, 0.95), 35),
        (74, (0.0, -0.22, 2.55), (0.0, 0.0, 0.95), 35),
    ],
)
camera(
    "shot6",
    [
        (0, (-1.15, -0.62, 1.05), (-0.55, -0.05, 0.96), 70),
        (89, (-0.45, -0.62, 1.05), (0.15, -0.05, 0.96), 70),
    ],
)
camera(
    "shot7",
    [
        (0, (0.9, -1.3, 1.5), (1.4, -0.1, 1.15), 35),
        (26, (1.5, -1.2, 1.5), (2.5, 0.0, 1.2), 35),
        (52, (0.55, -1.0, 2.75), (0.05, 0.15, 2.72), 28),
        (64, (0.05, -0.2, 2.5), (0.0, 0.2, 2.2), 18),
        (96, (0.03, -0.16, 1.2), (0.0, 0.2, 1.0), 18),
        (128, (-1.0, -1.6, 1.6), (0.0, 0.05, 1.0), 24),
        (164, (-1.6, -2.3, 2.15), (0.0, 0.05, 1.05), 24),
    ],
)
camera(
    "shot8",
    [
        (0, (-1.6, -2.3, 2.15), (0.0, 0.05, 1.05), 28),
        (34, (-0.45, -1.3, 1.3), (0.05, -0.05, 1.02), 50),
        (89, (-0.3, -1.15, 1.16), (PALM.x, PALM.y, PALM.z + 0.02), 85),
    ],
)
camera(
    "shot9",
    [
        (0, (-0.3, -1.15, 1.16), (PALM.x, PALM.y, PALM.z + 0.02), 85),
        (26, (-0.22, -1.13, 1.1), PLATE, 85),
        (59, (-0.18, -1.08, 1.08), PLATE, 85),
    ],
)

# ---------------------------------------------------------------- look, save, render
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x, scene.render.resolution_y = 960, 540
shading = scene.display.shading
shading.light, shading.color_type = "STUDIO", "MATERIAL"
shading.show_shadows, shading.show_cavity, shading.use_dof = True, True, True
scene.display.render_aa = "8"
scene.display.light_direction = (-0.6, 0.35, 0.72)  # from the north window, upper left

bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "lab_blockout.blend"))

if "--render" in ARGS:
    wanted = ARGS[ARGS.index("--shots") + 1].split(",") if "--shots" in ARGS else None
    plates = HERE.parent / "public" / "plates"
    plates.mkdir(parents=True, exist_ok=True)
    for shot in SHOTS["shots"]:
        number = shot["id"].removeprefix("shot")
        if wanted and number not in wanted:
            continue
        first, last = S[shot["id"]]
        scene.camera = bpy.data.objects[f"{shot['id']} camera"]
        if "--stills" in ARGS:
            scene.render.image_settings.file_format = "PNG"
            for label, frame in (("a", first + 2), ("b", (first + last) // 2), ("c", last - 2)):
                scene.frame_set(frame)
                scene.render.filepath = str(HERE / "stills" / f"{shot['id']}{label}.png")
                bpy.ops.render.render(write_still=True)
            continue
        settings = scene.render.image_settings
        if hasattr(settings, "media_type"):
            settings.media_type = "VIDEO"
        settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format, scene.render.ffmpeg.codec = "MPEG4", "H264"
        scene.render.ffmpeg.constant_rate_factor, scene.render.ffmpeg.gopsize = "HIGH", 6
        scene.frame_start, scene.frame_end = first, last
        scene.render.filepath = str(plates / f"{shot['id']}.mp4")
        bpy.ops.render.render(animation=True)
        print(f"rendered {shot['id']}: frames {first} to {last}")
