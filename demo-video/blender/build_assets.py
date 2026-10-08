"""Make the film's 3D objects: each one alone, as a GLB and as a picture with no background.

    blender -b -P demo-video/blender/build_assets.py
    blender -b -P demo-video/blender/build_assets.py -- logo phone

The objects are things from RADAR itself: its mark, the phone and the card its interface
lives on, and a token for each thing it tracks. Colours are the app's own (index.css).

Writes demo-video/public/assets/<name>.glb, <name>.png and assets.json, which records
each picture's size and, for the phone and the card, where the corners of the flat face
fall in the picture, so that Remotion can set a real interface into it. Remotion does
everything else: this script places no camera move and makes no shot.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

OUT = Path(__file__).resolve().parent.parent / "public" / "assets"
WANTED = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
SIZE = 1200
MANIFEST = {}


# ---------------------------------------------------------------- materials
def app(hex_colour):
    """One of the app's own colours, as the renderer wants it: linear, not screen."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)


def material(name, colour, metallic=0.0, roughness=0.5, transmission=0.0, coat=0.0, glow=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*colour, 1.0)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Transmission Weight"].default_value = transmission
    shader.inputs["Coat Weight"].default_value = coat
    shader.inputs["Emission Color"].default_value = (*colour, 1.0)
    shader.inputs["Emission Strength"].default_value = glow
    return mat


def palette():
    return {
        # The accent is a lit line on screen, so it glows a little here too.
        "accent": material("radar cyan", app("#62cfe8"), roughness=0.35, glow=1.6),
        "ink": material("ink white", app("#f3f4f7"), roughness=0.4, glow=0.6),
        "badge": material("badge", app("#0d1820"), roughness=0.3, coat=0.7),
        "screen": material("screen glass", app("#090a0e"), roughness=0.08, coat=1.0),
        "body": material("phone body", (0.05, 0.055, 0.065), metallic=1.0, roughness=0.3),
        "frost": material("card glass", (0.75, 0.82, 0.9), roughness=0.28, transmission=0.92),
        "bitcoin": material("bitcoin orange", app("#eea65b"), metallic=1.0, roughness=0.28),
        "gold": material("gold", (0.83, 0.6, 0.2), metallic=1.0, roughness=0.22),
        "stocks": material("stocks cyan", app("#62cfe8"), metallic=1.0, roughness=0.3),
        "cash": material("cash grey", app("#9ea2b0"), metallic=1.0, roughness=0.32),
    }


# ---------------------------------------------------------------- modelling helpers
def finish(obj, mat, bevel=0.0015, smooth=True):
    obj.data.materials.append(mat)
    if smooth:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    if bevel:
        modifier = obj.modifiers.new("edge", "BEVEL")
        modifier.width, modifier.segments, modifier.limit_method = bevel, 3, "ANGLE"
    return obj


def cylinder(name, radius, depth, location, mat, rotation=(0, 0, 0), bevel=0.0015):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, location=location, rotation=rotation, vertices=96
    )
    bpy.context.object.name = name
    return finish(bpy.context.object, mat, bevel)


def box(name, size, location, mat, bevel=0.0015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name, obj.scale = name, size
    bpy.ops.object.transform_apply(scale=True)
    return finish(obj, mat, bevel, smooth=False)


def ball(name, radius, location, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius, location=location, segments=64, ring_count=32
    )
    bpy.context.object.name = name
    return finish(bpy.context.object, mat, bevel=0.0)


def slab(name, width, height, radius, depth, mat, y=0.0, bevel=0.0006):
    """A rounded rectangle standing upright, facing the camera: a card, a screen, a badge.
    Its front face is at `y`; it is `depth` thick behind that."""
    points = []
    corners = (
        (width / 2 - radius, height / 2 - radius, 0),
        (-width / 2 + radius, height / 2 - radius, 90),
        (-width / 2 + radius, -height / 2 + radius, 180),
        (width / 2 - radius, -height / 2 + radius, 270),
    )
    for cx, cz, start in corners:
        for step in range(13):
            angle = math.radians(start + step * 7.5)
            points.append((cx + radius * math.cos(angle), y, cz + radius * math.sin(angle)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], [list(range(len(points)))])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    thick = obj.modifiers.new("thickness", "SOLIDIFY")
    thick.thickness, thick.offset = depth, -1.0  # grow backwards, away from the camera
    return finish(obj, mat, bevel, smooth=False)


def line(name, points, thickness, mat):
    """A round line through `points`: a chart line, a ring, a stroke of the mark."""
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions, data.bevel_depth, data.bevel_resolution = "3D", thickness, 6
    data.use_fill_caps = True
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, spot in zip(spline.points, points, strict=True):
        point.co = (*spot, 1.0)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def raised(name, text, size, location, mat, depth=0.0012, flat=False):
    """Lettering standing proud of a face: upright, or lying on a top face."""
    bpy.ops.object.text_add(location=location, rotation=(0, 0, 0) if flat else (math.pi / 2, 0, 0))
    obj = bpy.context.object
    obj.name, obj.data.body, obj.data.size = name, text, size
    obj.data.align_x, obj.data.align_y, obj.data.extrude = "CENTER", "CENTER", depth
    bpy.ops.object.convert(target="MESH")
    obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------- the studio
def studio(target, distance, azimuth=-22.0, elevation=8.0):
    """An empty scene, three soft lights, and a camera looking at `target`."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    preferences = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = kind
            preferences.refresh_devices()
            for device in preferences.devices:
                device.use = True
            scene.cycles.device = "GPU"
            break
        except (TypeError, RuntimeError):
            continue
    scene.cycles.samples, scene.cycles.use_denoising = 160, True
    scene.render.film_transparent = True
    scene.cycles.film_transparent_glass = True
    scene.render.resolution_x = scene.render.resolution_y = SIZE
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    world = bpy.data.worlds.new("studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.09, 0.1, 0.12, 1.0)
    scene.world = world

    aim = bpy.data.objects.new("aim", None)
    scene.collection.objects.link(aim)
    aim.location = target
    lights = [  # the app's one light from above and to the left, a weak fill, a rim
        ("key", (-0.8, -0.7, 0.9), 1.3, 60.0, (1.0, 0.99, 0.97)),
        ("fill", (1.0, -0.8, 0.2), 1.6, 12.0, (0.85, 0.94, 1.0)),
        ("rim", (0.6, 0.9, 0.7), 0.9, 45.0, (0.8, 0.95, 1.0)),
    ]
    for name, offset, size, power, colour in lights:
        data = bpy.data.lights.new(name, "AREA")
        data.size, data.energy, data.color = size, power, colour
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = Vector(target) + Vector(offset)
        track = light.constraints.new("TRACK_TO")
        track.target, track.track_axis, track.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"

    data = bpy.data.cameras.new("camera")
    data.lens, data.sensor_width, data.clip_start = 90, 36, 0.01
    camera = bpy.data.objects.new("camera", data)
    scene.collection.objects.link(camera)
    a, e = math.radians(azimuth), math.radians(elevation)
    camera.location = Vector(target) + distance * Vector(
        (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))
    )
    track = camera.constraints.new("TRACK_TO")
    track.target, track.track_axis, track.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = camera
    bpy.context.view_layer.update()
    return palette()


def shoot(name, face=None):
    """Export the object and photograph it. `face` is four corners of a flat face (top
    left, top right, bottom right, bottom left): where they fall in the picture is
    recorded, so that an interface can be set into that face."""
    scene, camera = bpy.context.scene, bpy.context.scene.camera
    OUT.mkdir(parents=True, exist_ok=True)
    entry = {"size": SIZE, "glb": f"{name}.glb", "image": f"{name}.png"}
    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT / f"{name}.glb"), use_selection=True, export_apply=True
    )
    scene.render.filepath = str(OUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    if face:
        bpy.context.view_layer.update()
        entry["face"] = []
        for corner in face:
            seen = world_to_camera_view(scene, camera, Vector(corner))
            entry["face"].append([round(seen.x * SIZE, 1), round((1 - seen.y) * SIZE, 1)])
    MANIFEST[name] = entry
    print(f"made {name}")


# ---------------------------------------------------------------- the objects
def logo():
    """The app's own mark (Layout.tsx, RadarMark), built in relief. It is drawn on a
    grid of 32 units; `spot` turns a point of that drawing into a place on the badge."""
    m = studio((0, 0, 0), 0.5, azimuth=-20, elevation=8)
    unit = 0.1 / 32

    def spot(x, y, lift=0.0):
        return ((x - 16) * unit, -lift, (16 - y) * unit)

    slab("badge rim", 0.1, 0.1, 0.03, 0.006, m["accent"], y=0.0025, bevel=0.0)
    slab("badge", 0.096, 0.096, 0.028, 0.009, m["badge"], bevel=0.0012)
    ring = [
        spot(15 + 8.5 * math.cos(math.radians(a)), 17 + 8.5 * math.sin(math.radians(a)), 0.0008)
        for a in range(0, 361, 6)
    ]
    line("ring", ring, 0.001, m["stocks"])
    stroke = [
        spot(7.5, 21.5, 0.003),
        spot(12.5, 16.5, 0.003),
        spot(16, 19.5, 0.003),
        spot(24.5, 10, 0.003),
    ]
    line("chart line", stroke, 0.0036, m["accent"])
    ball("chart point", 0.0062, spot(24.5, 10, 0.004), m["ink"])
    shoot("logo")


def phone():
    m = studio((0, 0, 0), 0.56)
    slab("phone body", 0.074, 0.154, 0.013, 0.008, m["body"], bevel=0.0015)
    slab("phone screen", 0.068, 0.148, 0.0105, 0.0006, m["screen"], y=-0.0006, bevel=0.0)
    box("side button", (0.0015, 0.004, 0.02), (0.0378, 0.004, 0.03), m["body"], bevel=0.0005)
    w, h, y = 0.034, 0.074, -0.0007
    shoot("phone", face=[(-w, y, h), (w, y, h), (w, y, -h), (-w, y, -h)])


def card():
    """One of the app's translucent cards, as an object."""
    m = studio((0, 0, 0), 0.6, azimuth=-18)
    slab("card", 0.2, 0.125, 0.014, 0.005, m["frost"], bevel=0.0012)
    w, h, y = 0.1, 0.0625, -0.0002
    shoot("card", face=[(-w, y, h), (w, y, h), (w, y, -h), (-w, y, -h)])


def coin(name, metal, mark):
    """A token for one thing the app tracks, in that thing's colour in the app."""
    m = studio((0, 0, 0), 0.34, azimuth=-20, elevation=10)
    turn = (math.pi / 2, 0, 0)
    cylinder("coin", 0.04, 0.009, (0, 0.0045, 0), m[metal], rotation=turn, bevel=0.0014)
    cylinder("coin field", 0.0345, 0.002, (0, 0.0006, 0), m["badge"], rotation=turn, bevel=0.0)
    if mark == "chart":
        rise = [
            (-0.02, -0.0012, -0.012),
            (-0.008, -0.0012, -0.001),
            (0.002, -0.0012, -0.008),
            (0.021, -0.0012, 0.014),
        ]
        line("coin chart", rise, 0.0028, m[metal])
    else:
        raised("coin mark", mark, 0.044, (0, -0.0004, 0), m[metal], depth=0.0014)
    shoot(name)


def gold_bar():
    m = studio((0, 0, 0.012), 0.4, azimuth=-28, elevation=24)
    bar = box("gold bar", (0.11, 0.05, 0.026), (0, 0, 0.013), m["gold"], bevel=0.0018)
    for vertex in bar.data.vertices:  # an ingot narrows towards the top
        if vertex.co.z > 0:
            vertex.co.x *= 0.86
            vertex.co.y *= 0.76
    raised("gold stamp", "GOLD", 0.014, (0, 0, 0.026), m["gold"], depth=0.0006, flat=True)
    shoot("gold")


OBJECTS = {
    "logo": logo,
    "phone": phone,
    "card": card,
    "bitcoin": lambda: coin("bitcoin", "bitcoin", "B"),
    "stocks": lambda: coin("stocks", "stocks", "chart"),
    "cash": lambda: coin("cash", "cash", "$"),
    "gold": gold_bar,
}
for name, make in OBJECTS.items():
    if not WANTED or name in WANTED:
        make()

record = OUT / "assets.json"
known = json.loads(record.read_text(encoding="utf-8")) if record.exists() else {}
record.write_text(json.dumps(known | MANIFEST, indent=2) + "\n", encoding="utf-8")
