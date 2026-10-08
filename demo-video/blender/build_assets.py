"""Make the reel's 3D objects as GLBs: the phone, and the Bitcoin coin.

    blender -b -P demo-video/blender/build_assets.py

These two and the mark (drawn in code) are the only objects in the film; everything else
is the app's interface in two dimensions.

The phone is a generic modern one with no maker's shapes or marks: a metal frame with
rounded corners, glass front and back, a small camera bump and two side buttons. The
coin (kit.glb) is struck with the Bitcoin sign on both faces and has a reeded edge. Each
part is its own object and carries a material named for what it is; Remotion swaps those
names for its own materials and puts the interface on the phone's "screen". This script
places no camera and makes no shot.

The phone's lengths are metres; the coin's are the film's own units, and its size is
written beside it (src/three/kit.json). The face looks along +Z and the top is +Y, and
the files are written without the usual axis swap, so the same holds in Remotion.
"""

import json
import math
from pathlib import Path

import bmesh
import bpy

OUT = Path(__file__).resolve().parent.parent / "public" / "assets"

WIDTH, HEIGHT, DEPTH = 0.0715, 0.1478, 0.0080
CORNER = 0.0125
# The lit screen stops this far from the frame. Its shape matches the photographs of the
# app (1170 by 2532), so they sit on it without stretching.
BEZEL = 0.0030
FRONT = DEPTH / 2
BACK = -DEPTH / 2


def material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat


def outline(width, height, radius, steps=20):
    """A rectangle with round corners, anticlockwise seen from +Z."""
    points = []
    half_w, half_h = width / 2 - radius, height / 2 - radius
    for cx, cy, start in (
        (half_w, half_h, 0),
        (-half_w, half_h, 90),
        (-half_w, -half_h, 180),
        (half_w, -half_h, 270),
    ):
        for i in range(steps + 1):
            angle = math.radians(start + 90 * i / steps)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def add(name, mesh, mat, bevel=0.0, segments=4):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    mesh.materials.append(mat)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if bevel:
        edge = obj.modifiers.new("edge", "BEVEL")
        edge.width, edge.segments, edge.limit_method = bevel, segments, "ANGLE"
        edge.angle_limit = math.radians(40)
        # Flat faces stay flat and only the rounded edge shades as a curve.
        normals = obj.modifiers.new("normals", "WEIGHTED_NORMAL")
        normals.keep_sharp = False
    return obj


def slab(name, width, height, radius, z_from, z_to, mat, at=(0.0, 0.0), bevel=0.0, segments=4):
    """A rounded rectangle with thickness."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    face = bm.faces.new(
        [bm.verts.new((x + at[0], y + at[1], z_from)) for x, y in outline(width, height, radius)]
    )
    lifted = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(
        bm,
        vec=(0, 0, z_to - z_from),
        verts=[g for g in lifted["geom"] if isinstance(g, bmesh.types.BMVert)],
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return add(name, mesh, mat, bevel, segments)


def plate(name, width, height, radius, z, mat, faces_back=False, mapped=False):
    """A flat rounded rectangle. With `mapped`, a picture laid on it fills it exactly."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    points = outline(width, height, radius, steps=28)
    if faces_back:
        points.reverse()
    face = bm.faces.new([bm.verts.new((x, y, z)) for x, y in points])
    if mapped:
        layer = bm.loops.layers.uv.new("picture")
        for loop in face.loops:
            loop[layer].uv = (loop.vert.co.x / width + 0.5, loop.vert.co.y / height + 0.5)
    bmesh.ops.triangulate(bm, faces=[face])
    bm.to_mesh(mesh)
    bm.free()
    return add(name, mesh, mat)


def disc(name, radius, depth, centre, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=centre, vertices=72)
    obj = bpy.context.object
    obj.name = name
    mesh = obj.data
    bpy.context.collection.objects.unlink(obj)
    bpy.data.objects.remove(obj)
    return add(name, mesh, mat, bevel, 3)


def phone():
    metal, glass, back = material("metal"), material("glass"), material("back")
    screen, sheen, lens, flash = (
        material("screen"),
        material("sheen"),
        material("lens"),
        material("flash"),
    )

    # The frame: one band of metal, its two rims rounded over.
    slab("frame", WIDTH, HEIGHT, CORNER, BACK, FRONT, metal, bevel=0.0016, segments=6)

    # Front: black glass almost to the rim, the lit screen inside it, and a clear sheet
    # over the screen so that it still catches the room.
    rim = 0.0011
    plate("front glass", WIDTH - 2 * rim, HEIGHT - 2 * rim, CORNER - rim, FRONT + 0.00004, glass)
    lit = (WIDTH - 2 * BEZEL, HEIGHT - 2 * BEZEL, CORNER - BEZEL)
    plate("screen", *lit, FRONT + 0.00008, screen, mapped=True)
    plate("screen sheen", *lit, FRONT + 0.00012, sheen)
    disc("front camera", 0.0016, 0.00004, (0, HEIGHT / 2 - 0.0068, FRONT + 0.00016), lens)

    # Back: frosted glass, and a low pill carrying two lenses and a flash.
    plate(
        "back glass",
        WIDTH - 2 * rim,
        HEIGHT - 2 * rim,
        CORNER - rim,
        BACK - 0.00004,
        back,
        faces_back=True,
    )
    bump_at = (WIDTH / 2 - 0.0195, HEIGHT / 2 - 0.0330)
    bump_top = BACK - 0.0015
    slab("camera bump", 0.0230, 0.0460, 0.0115, BACK, bump_top, glass, at=bump_at, bevel=0.0006)
    for i, dy in enumerate((0.0110, -0.0110)):
        centre = (bump_at[0], bump_at[1] + dy)
        disc(f"lens ring {i}", 0.0082, 0.0011, (*centre, bump_top - 0.00045), metal, bevel=0.0003)
        disc(f"lens {i}", 0.0064, 0.0002, (*centre, bump_top - 0.00105), lens)
    disc("flash", 0.0026, 0.0003, (bump_at[0] - 0.0185, bump_at[1] + 0.0110, BACK - 0.00015), flash)

    # Two buttons on one side.
    for name, y, length in (("power", 0.0180, 0.0170), ("volume", 0.0470, 0.0260)):
        slab(name, 0.0030, length, 0.0012, 0, 0.0009, metal, bevel=0.0003)
        button = bpy.data.objects[name]
        button.rotation_euler = (0, math.radians(90), 0)
        button.location = (WIDTH / 2 - 0.0002, y, 0)


def join(name, parts):
    """Several objects made one, under one name, at the origin."""
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    parts[0].name = name
    return parts[0]


def box(name, size, at, mat, bevel=0.0, segments=4):
    """A box with rounded edges, `size` wide, tall and deep, centred on `at`."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=at, verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    return add(name, mesh, mat, bevel, segments)


def letters(name, text, size, depth, mat, bevel=0.0):
    """Text as a solid, lying in the XY plane and facing +Z, its foot on y = 0."""
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text
    curve.size = size
    curve.extrude = depth / 2
    curve.bevel_depth = bevel
    curve.bevel_resolution = 3
    curve.resolution_u = 12
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def centre(obj, x=True, y=True):
    """Move an object's points so that its box is centred on the origin in x and y."""
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    dx = -(min(xs) + max(xs)) / 2 if x else 0.0
    dy = -(min(ys) + max(ys)) / 2 if y else 0.0
    for v in obj.data.vertices:
        v.co.x += dx
        v.co.y += dy
    return max(xs) - min(xs), max(ys) - min(ys)


COIN_RADIUS, COIN_DEPTH = 0.5, 0.075


def coin():
    """A minted coin lying in the XY plane: a reeded edge, a raised rim on each face, and
    the Bitcoin sign struck on both. The sign is the letter B with two short strokes
    above and below it, as the sign is drawn."""
    metal, relief = material("coin"), material("coin relief")
    parts = []

    # The body, its edge cut into fine reeds.
    mesh = bpy.data.meshes.new("coin body")
    bm = bmesh.new()
    reeds = 150
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=reeds * 2,
        radius1=COIN_RADIUS,
        radius2=COIN_RADIUS,
        depth=COIN_DEPTH,
    )
    for vert in bm.verts:
        angle = math.atan2(vert.co.y, vert.co.x)
        step = round(angle / (math.pi / reeds))
        if step % 2 and abs(math.hypot(vert.co.x, vert.co.y) - COIN_RADIUS) < 1e-4:
            vert.co.x *= 0.988
            vert.co.y *= 0.988
    bm.to_mesh(mesh)
    bm.free()
    body = add("coin body", mesh, metal)
    for polygon in body.data.polygons:
        polygon.use_smooth = False
    parts.append(body)

    for side in (1, -1):
        z = side * COIN_DEPTH / 2
        # The rim: a low ring standing proud of the face.
        bpy.ops.mesh.primitive_torus_add(
            major_radius=COIN_RADIUS - 0.03,
            minor_radius=0.016,
            major_segments=160,
            minor_segments=10,
            location=(0, 0, z),
        )
        rim = bpy.context.object
        rim.data.materials.append(relief)
        bpy.ops.object.shade_smooth()
        parts.append(rim)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=COIN_RADIUS - 0.085,
            minor_radius=0.005,
            major_segments=160,
            minor_segments=8,
            location=(0, 0, z),
        )
        inner = bpy.context.object
        inner.data.materials.append(relief)
        bpy.ops.object.shade_smooth()
        parts.append(inner)

        sign = letters("sign", "B", 0.62, 0.03, relief, bevel=0.004)
        centre(sign)
        height = max(v.co.y for v in sign.data.vertices)
        strokes = [sign]
        for x in (-0.075, 0.035):
            for y in (height + 0.02, -height - 0.02):
                strokes.append(box("stroke", (0.045, 0.09, 0.03), (x - 0.02, y, 0), relief, 0.004))
        sign = join("sign", strokes)
        bpy.ops.object.select_all(action="DESELECT")
        sign.select_set(True)
        bpy.context.view_layer.objects.active = sign
        bpy.ops.object.convert(target="MESH")
        sign = bpy.context.object
        sign.location = (0, 0, z)
        if side < 0:
            sign.rotation_euler = (0, math.pi, 0)
        parts.append(sign)

    return join("coin", parts)


def export(name):
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT / name),
        export_format="GLB",
        export_apply=True,
        export_yup=False,
        export_materials="EXPORT",
    )


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    phone()
    export("phone.glb")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    coin()
    export("kit.glb")
    sizes = {"coin": {"radius": COIN_RADIUS, "depth": COIN_DEPTH}}
    notes = OUT.parent.parent / "src" / "three" / "kit.json"
    notes.write_text(json.dumps(sizes, indent=2) + "\n", encoding="utf8")


main()
