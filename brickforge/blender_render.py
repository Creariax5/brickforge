"""Rendu photoréaliste d'un modèle avec Blender Cycles (exécuté DANS Blender).

    blender -b --factory-startup -P brickforge/blender_render.py -- job.json

job.json :
    {"parts": [{"part": "3001", "color": 4, "m": [x,y,z, a..i]}, ...],    (repère LDraw)
     "camera": {"pos": [x,y,z], "target": [x,y,z], "fov": 35, "aspect": 1.6},  (repère Three : LDraw × (1/20, -1/20, 1/20))
     "out": "chemin.png", "width": 1600, "samples": 96}
    ou {"parts": [...], "glb": "chemin.glb"} : exporte seulement le modèle biseauté en glTF (pour le rendu progressif du navigateur)

Ce qui fait le réalisme :
  - arêtes biseautées (biseau appliqué une fois par pièce, puis instances liées) qui accrochent la lumière ;
  - normales lissées au-delà de 35° (pièces rondes sans facettes) ;
  - plastique ABS : Principled BSDF avec vernis (coat), légère diffusion sous la surface, transparents en transmission ;
  - studio : grande softbox principale, contre-jour, remplissage, réflexions visibles dans le plastique ;
  - sol « attrape-ombres » sur fond transparent : l'ombre est gardée, le fond est composé ensuite.
"""

import json
import math
import re
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from brickforge.ldlib import part_triangles  # noqa: E402

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
S = 1 / 20                                         # 1 unité Blender = 1 tenon
THREE_TO_BL = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))   # Three (Y haut) → Blender (Z haut)


# ---------------------------------------------------------------- couleurs LDraw

def ldconfig():
    cols = {}
    for l in (ROOT / "data" / "ldraw" / "LDConfig.ldr").read_text(errors="ignore").splitlines():
        m = re.match(r"0 !COLOUR (\S+)\s+CODE\s+(\d+)\s+VALUE\s+#([0-9A-Fa-f]{6})(.*)", l)
        if m:
            a = re.search(r"ALPHA\s+(\d+)", m.group(4))
            kind = next((k for k in ("CHROME", "PEARLESCENT", "METAL", "RUBBER", "MATTE_METALLIC") if k in m.group(4)), "")
            cols[int(m.group(2))] = (m.group(3), int(a.group(1)) / 255 if a else 1.0, kind)
    return cols


COLS = ldconfig()


def srgb2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


_mats = {}


def material(code):
    if code in _mats:
        return _mats[code]
    hx, alpha, kind = COLS.get(code, ("9BA19D", 1.0, ""))
    rgb = [srgb2lin(int(hx[i:i + 2], 16) / 255) for i in (0, 2, 4)]
    m = bpy.data.materials.new(f"ld{code}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = 0.22
    b.inputs["IOR"].default_value = 1.46
    b.inputs["Coat Weight"].default_value = 0.25
    b.inputs["Coat Roughness"].default_value = 0.08
    if alpha < 1:                                   # transparents : verre coloré
        b.inputs["Transmission Weight"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.04
        b.inputs["Coat Weight"].default_value = 0.0
    elif kind in ("CHROME", "METAL", "MATTE_METALLIC"):
        b.inputs["Metallic"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.12 if kind == "CHROME" else 0.3
    elif kind == "PEARLESCENT":
        b.inputs["Metallic"].default_value = 0.6
        b.inputs["Roughness"].default_value = 0.28
    elif kind == "RUBBER":
        b.inputs["Roughness"].default_value = 0.7
        b.inputs["Coat Weight"].default_value = 0.0
    else:                                           # ABS : un soupçon de diffusion sous la surface
        b.inputs["Subsurface Weight"].default_value = 0.08
        b.inputs["Subsurface Radius"].default_value = (rgb[0] + .05, rgb[1] + .05, rgb[2] + .05)
        b.inputs["Subsurface Scale"].default_value = 0.02
    _mats[code] = m
    return m


# ---------------------------------------------------------------- pièces : maillage biseauté, une fois par référence

_meshes = {}


def part_mesh(part):
    if part in _meshes:
        return _meshes[part]
    tris = part_triangles(part).reshape(-1, 3).astype(np.float64)
    if not len(tris):
        _meshes[part] = None
        return None
    me = bpy.data.meshes.new(part)
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in tris]
    for i in range(0, len(vs), 3):
        try:
            bm.faces.new(vs[i:i + 3])
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.05)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.01)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    # biseau des arêtes vives (0,35 LDU), appliqué pour que toutes les instances le partagent
    ob = bpy.data.objects.new("tmp_" + part, me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("bevel", "BEVEL")
    mod.width = 0.35
    mod.segments = 2
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(40)
    mod.use_clamp_overlap = True
    mod.harden_normals = False
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    me2.polygons.foreach_set("use_smooth", [True] * len(me2.polygons))
    me2.set_sharp_from_angle(angle=math.radians(35))
    _meshes[part] = me2
    return me2


# ---------------------------------------------------------------- scène

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
col = scene.collection
for p in job["parts"]:
    me = part_mesh(p["part"])
    if me is None:
        continue
    x, y, z, a, b, c, d, e, f, g, h, i = p["m"]
    M = Matrix(((a, b, c, x), (d, e, f, y), (g, h, i, z), (0, 0, 0, 1)))
    W = Matrix.Diagonal((S, -S, S, 1.0))
    ob = bpy.data.objects.new(p["part"], me)
    ob.matrix_world = THREE_TO_BL.to_4x4() @ W @ M
    if not me.materials:
        me.materials.append(None)
    ob.material_slots[0].link = "OBJECT"
    ob.material_slots[0].material = material(p["color"])
    col.objects.link(ob)

# export glTF (pièces biseautées, matériaux PBR) pour le traceur de chemins temps réel du navigateur
if job.get("glb"):
    bpy.ops.export_scene.gltf(filepath=job["glb"], export_format="GLB", use_selection=False, export_yup=True,
                              export_cameras=False, export_lights=False, export_materials="EXPORT", export_apply=False)
    print("BF glb", flush=True)
    sys.exit(0)

# boîte englobante du modèle (repère Blender)
pts = [ob.matrix_world @ Vector(cn) for ob in col.objects for cn in ob.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr, size = (lo + hi) / 2, max((hi - lo).length, 1.0)

# sol attrape-ombres
bpy.ops.mesh.primitive_plane_add(size=size * 30, location=(ctr.x, ctr.y, lo.z - 0.001))
floor = bpy.context.active_object
floor.is_shadow_catcher = True

# caméra : celle de la vue 3D de l'app
cam = job["camera"]
cpos = THREE_TO_BL @ Vector(cam["pos"])
ctgt = THREE_TO_BL @ Vector(cam["target"])
cd = bpy.data.cameras.new("cam")
cd.sensor_fit = "VERTICAL"
cd.angle_y = math.radians(cam["fov"])
cd.clip_start, cd.clip_end = size / 500, size * 50
camo = bpy.data.objects.new("cam", cd)
camo.location = cpos
camo.rotation_euler = (ctgt - cpos).to_track_quat("-Z", "Y").to_euler()
col.objects.link(camo)
scene.camera = camo

# éclairage studio : softbox principale au-dessus/devant, contre-jour, remplissage


def area(name, energy, size_, loc_dir, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy * size * size
    ld.size = size_ * size
    ld.color = color
    lo_ = bpy.data.objects.new(name, ld)
    view = (cpos - ctgt).normalized()
    side = view.cross(Vector((0, 0, 1))).normalized()
    pos = ctgt + (view * loc_dir[0] + side * loc_dir[1] + Vector((0, 0, 1)) * loc_dir[2]).normalized() * size * 2.2
    lo_.location = pos
    lo_.rotation_euler = (ctgt - pos).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(lo_)


area("key", 55, 1.2, (0.6, 0.7, 1.0))
area("fill", 14, 1.6, (0.8, -1.0, 0.25), (0.95, 0.97, 1.0))
area("rim", 40, 0.8, (-1.0, 0.3, 0.9))
area("top", 18, 2.0, (0.0, 0.0, 1.0))

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
scene.world = world

# rendu
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = int(job.get("samples", 96))
scene.cycles.use_adaptive_sampling = True
scene.cycles.adaptive_threshold = 0.02
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.transmission_bounces = 8
scene.render.threads_mode = "FIXED"
scene.render.threads = int(job.get("threads", 12))
scene.render.film_transparent = True
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Punchy"
w = int(job.get("width", 1600))
scene.render.resolution_x = w
scene.render.resolution_y = int(round(w / cam.get("aspect", 1.6)))
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = job["out"]
print(f"BF parts={len(col.objects)} samples={scene.cycles.samples} size={scene.render.resolution_x}x{scene.render.resolution_y}", flush=True)
bpy.ops.render.render(write_still=True)
print("BF done", flush=True)
