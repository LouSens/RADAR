"""Make the reel's phone as a GLB.

    blender -b -P demo-video/blender/build_assets.py

A generic modern phone with no maker's shapes or marks: a metal frame with rounded
corners, glass front and back, a small camera bump and two side buttons. Each part is
its own object and carries a material named for what it is (metal, glass, back, screen,
sheen, lens, flash); Remotion swaps those names for its own materials and puts the
interface on "screen". This script places no camera and makes no shot.

Lengths are metres. The face looks along +Z and the top is +Y, and the file is written
without the usual axis swap, so the same holds in Remotion.
"""

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


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    phone()
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(OUT / "phone.glb"),
        export_format="GLB",
        export_apply=True,
        export_yup=False,
        export_materials="EXPORT",
    )


main()
