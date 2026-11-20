# Convert Nikki_2.0.blend into a clean rig + skinned FBX with REAL baked textures.
# Bakes each garment/body part's diffuse color into one atlas per slot (Skin/Face/Hair/Cloth).
# Run: blender -b Nikki_2.0.blend -P export_fbx_real.py -- <out_fbx> <out_texdir> [resolution]
import bpy, os, sys, json, math
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_FBX, OUT_TEX = argv[0], argv[1]
RES = int(argv[2]) if len(argv) > 2 else 2048
os.makedirs(os.path.dirname(OUT_FBX), exist_ok=True)
os.makedirs(OUT_TEX, exist_ok=True)
def log(*a): print('NKEXP', *a, flush=True)

CHARMESH = {
 'body nikki':'Skin','EyeBall.nikki':'Face','cornea':'Face','eyelashes nikki':'Face',
 'teeth nikki':'Face','tongue nikki':'Face','hair':'Hair','hair.001':'Hair','hairclip':'Hair',
 'dress':'Cloth','dress.001':'Cloth','shoes':'Cloth','shoes.001':'Cloth','socks':'Cloth','socks.001':'Cloth',
 'shorts':'Cloth','shorts.001':'Cloth','sleeves':'Cloth','sleeves1':'Cloth','choker':'Cloth',
 'hat':'Hair','neckwear':'Cloth',
}

# ---- 1. keep only char meshes + rig.003 ----
arm_obj = bpy.data.objects.get('rig.003')
assert arm_obj, 'no rig.003'
keep_objs = set(CHARMESH) | {'rig.003'}
for o in list(bpy.data.objects):
    if o.name in keep_objs: continue
    bpy.data.objects.remove(o, do_unlink=True)
meshes = [bpy.data.objects[n] for n in CHARMESH if n in bpy.data.objects]
log('meshes kept', len(meshes), [m.name for m in meshes])

arm_obj.parent = None
for m in meshes:
    mw = m.matrix_world.copy(); m.parent = None; m.matrix_world = mw

# ---- 1b. fix cloth meshes that are wrongly skinned to the arm bones ----
# (skirt/choker/neckwear follow arms in game because their weights sit on shoulder/arm/hand)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wgfix
tgt = [bpy.data.objects[n] for n in ('dress', 'dress.001', 'choker', 'neckwear') if n in bpy.data.objects]
wgfix.apply(bpy, arm_obj, tgt, log)
# bare arm skin + sleeve accessories: rebind source-only arm helper bones to the
# drivable canonical arm chain, otherwise the elbow tears apart when the arm bends.
armfix = [bpy.data.objects[n] for n in ('body nikki', 'sleeves', 'sleeves1') if n in bpy.data.objects]
wgfix.fix_body_arm(bpy, arm_obj, armfix, log)
# outer skirt is skinned to root.x (rigid) -> rebind to the c_skirt physics chain so
# the legs (kinematic colliders) push it instead of poking through.
skirtfix = [bpy.data.objects[n] for n in ('dress',) if n in bpy.data.objects]
wgfix.fix_skirt_rigid(bpy, arm_obj, skirtfix, log)

# ---- 2. clean armature hierarchy ----
arm = arm_obj.data
orig_parent = {b.name: (b.parent.name if b.parent else None) for b in arm.bones}
weighted = set()
for m in meshes:
    for g in m.vertex_groups:
        if g.name in arm.bones:
            weighted.add(g.name)
log('weighted bones', len(weighted), 'of', len(arm.bones))

LR = [('l','Left'),('r','Right')]
parent_map = {
 'root.x': None,
 'spine_01.x':'root.x','spine_02.x':'spine_01.x','spine_03.x':'spine_02.x',
 'spine_04.x':'spine_03.x','spine_05.x':'spine_04.x',
 'neck.x':'spine_05.x','head.x':'neck.x',
}
for s,_ in LR:
    parent_map.update({
      f'shoulder.{s}':'spine_05.x', f'arm.{s}':f'shoulder.{s}', f'forearm.{s}':f'arm.{s}', f'hand.{s}':f'forearm.{s}',
      f'thigh.{s}':'root.x', f'leg.{s}':f'thigh.{s}', f'foot.{s}':f'leg.{s}', f'toes_01.{s}':f'foot.{s}',
    })
    for f in ('thumb','index','middle','ring','pinky'):
        parent_map[f'{f}1.{s}'] = f'hand.{s}'

anchor_names = ['root.x','spine_01.x','spine_02.x','spine_03.x','spine_04.x','spine_05.x','neck.x','head.x']
for s,_ in LR:
    anchor_names += [f'shoulder.{s}',f'arm.{s}',f'forearm.{s}',f'hand.{s}',f'thigh.{s}',f'leg.{s}',f'foot.{s}',f'toes_01.{s}']
anchor_pos = {n:arm.bones[n].head_local.copy() for n in anchor_names if n in arm.bones}
def nearest_anchor(p):
    best=None; bd=1e18
    for n,h in anchor_pos.items():
        d=(p-h).length_squared
        if d<bd: bd=d; best=n
    return best

# cloth/skirt/tail helper bones must follow the torso, never arms/legs.
# otherwise nearest_anchor grabs hand/thigh and the skirt swings with the arms.
torso_names = ['root.x','spine_01.x','spine_02.x','spine_03.x','spine_04.x','spine_05.x','neck.x','head.x']
torso_pos = {n:arm.bones[n].head_local.copy() for n in torso_names if n in arm.bones}
def nearest_torso(p):
    best=None; bd=1e18
    for n,h in torso_pos.items():
        d=(p-h).length_squared
        if d<bd: bd=d; best=n
    return best
CLOTH_KW = ('skirt','cloth','capat','armwing','add_tail','pelvis','necklace','hair')
def is_clothish(n):
    ln=n.lower()
    return any(k in ln for k in CLOTH_KW)

kept = set(n for n in weighted if n in arm.bones)
for n in parent_map:
    if n in arm.bones: kept.add(n)
for n in anchor_names:
    if n in arm.bones: kept.add(n)

bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.edit_bones
for b in eb: b.use_connect=False
for n in kept:
    if n not in eb: continue
    if n in parent_map:
        p = parent_map[n]
    else:
        # preserve the original parent chain (skip ancestors that were dropped),
        # so cloth/hair/tail chains stay connected for physics.
        p = None
        q = orig_parent.get(n); seen = set()
        while q is not None and q not in seen:
            seen.add(q)
            if q in kept and q != n:
                p = q; break
            q = orig_parent.get(q)
        if p is None:
            # no kept ancestor: attach the chain root to a torso/head anchor (never arms/legs)
            p = nearest_torso(arm.bones[n].head_local) if is_clothish(n) else nearest_anchor(arm.bones[n].head_local)
    if p and p in eb and p != n: eb[n].parent = eb[p]
    else: eb[n].parent = None
todo = [b.name for b in list(eb) if b.name not in kept]
log('removing bones', len(todo))
for n in todo:
    if n in eb: eb.remove(eb[n])
for b in list(eb):
    if b.parent is None and b.name != 'root.x':
        p = nearest_anchor(b.head)
        if p and p in eb and p != b.name: b.parent = eb[p]
        else: b.parent = eb['root.x']
log('roots now', [b.name for b in eb if b.parent is None])
import re as _re
ren = {}
existing = set(b.name for b in eb)
for b in list(eb):
    clean = _re.sub(r'[^A-Za-z0-9_]', '_', b.name)
    if clean != b.name and clean not in existing: ren[b.name] = clean
for old, new in ren.items(): eb[old].name = new
bpy.ops.object.mode_set(mode='OBJECT')
for m in meshes:
    for g in m.vertex_groups:
        if g.name in ren: g.name = ren[g.name]
log('sanitize renamed', len(ren), 'bones after clean', len(arm.bones))

# ---- 3. build UV atlas groups per slot and bake diffuse color ----
# For every (mesh, material) group we map its original-UV faces into a disjoint cell of the slot atlas.
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.samples = 1
bpy.context.scene.cycles.use_denoising = False
bpy.context.scene.render.bake.margin = 4
bpy.context.scene.render.bake.use_selected_to_active = False
try:
    bpy.context.scene.cycles.device = 'CPU'
except Exception:
    pass

SLOTS = {'Skin':'Skin','Face':'Face','Hair':'Hair','Cloth':'Cloth'}

def ensure_uv_orig(mat, uvname):
    nt = mat.node_tree
    uvn = nt.nodes.get('UV_ORIG')
    if uvn is None:
        uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = uvname; uvn.name = 'UV_ORIG'; uvn.label = 'UV_ORIG'
    touched = set()
    for n in list(nt.nodes):
        if n.type != 'TEX_IMAGE': continue
        vec = n.inputs.get('Vector')
        if vec is None: continue
        if not vec.is_linked:
            nt.links.new(uvn.outputs['UV'], vec); continue
        src = vec.links[0].from_node
        if src.type == 'TEX_COORD':
            nt.links.new(uvn.outputs['UV'], vec)
        elif src.type == 'MAPPING' and id(src) not in touched:
            touched.add(id(src))
            mvec = src.inputs.get('Vector')
            if mvec is not None:
                nt.links.new(uvn.outputs['UV'], mvec)

def add_bake_target(mat, img):
    nt = mat.node_tree
    tn = nt.nodes.get('BAKE_TARGET')
    if tn is None:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.name = 'BAKE_TARGET'
    tn.image = img
    for n in nt.nodes: n.select = False
    tn.select = True
    nt.nodes.active = tn
    return tn

def alpha_source(mat):
    """返回材质透明度来源：('link', from_socket) 或 ('const', 值)。"""
    bsdfs = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
    for b in bsdfs:
        a = b.inputs.get('Alpha')
        if a and a.is_linked:
            return ('link', a.links[0].from_socket)
    for b in bsdfs:
        a = b.inputs.get('Alpha')
        if a and not a.is_linked and abs(float(a.default_value) - 1.0) > 1e-4:
            return ('const', float(a.default_value))
    return ('const', 1.0)

def bake_alpha_into(color_img, slot_objs, slot):
    """把每个材质的不透明度烘成灰度图，写进 color_img 的 alpha 通道。"""
    aimg = bpy.data.images.new('ALPHA_' + slot, RES, RES, alpha=True)
    aimg.colorspace_settings.name = 'Non-Color'
    for o in slot_objs:
        for ms in o.material_slots:
            mat = ms.material
            if not mat or not mat.use_nodes:
                continue
            nt = mat.node_tree
            outs = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL']
            if not outs:
                continue
            kind, val = alpha_source(mat)
            em = nt.nodes.new('ShaderNodeEmission')
            em.inputs['Strength'].default_value = 1.0
            if kind == 'link':
                nt.links.new(val, em.inputs['Color'])
            else:
                v = float(val); em.inputs['Color'].default_value = (v, v, v, 1.0)
            nt.links.new(em.outputs['Emission'], outs[0].inputs['Surface'])
            add_bake_target(mat, aimg)
    bpy.context.view_layer.objects.active = slot_objs[0]
    with bpy.context.temp_override(active_object=slot_objs[0], object=slot_objs[0],
                                   selected_objects=slot_objs, selected_editable_objects=slot_objs):
        bpy.ops.object.bake(type='EMIT', margin=4, use_clear=True)
    ca = np.empty(RES * RES * 4, np.float32); color_img.pixels.foreach_get(ca)
    aa = np.empty(RES * RES * 4, np.float32); aimg.pixels.foreach_get(aa)
    ca = ca.reshape(-1, 4); aa = aa.reshape(-1, 4)
    ca[:, 3] = aa[:, 0]
    color_img.pixels.foreach_set(np.ascontiguousarray(ca.ravel(), np.float32))
    color_img.update()
    try: bpy.data.images.remove(aimg)
    except Exception: pass

slot_meshes = {s: [] for s in SLOTS}
for m in meshes:
    slot_meshes[CHARMESH.get(m.name, 'Cloth')].append(m)

atlas_paths = {}
for slot, objs in slot_meshes.items():
    if not objs:
        continue
    # gather groups (obj, mat_index, polys, orig uv bbox); ensure each obj has an 'Atlas' uv layer
    groups = []
    for ob in objs:
        me = ob.data
        uvl = me.uv_layers.active
        orig_name = uvl.name
        # make sure materials read original uv while we bake into Atlas
        for ms in ob.material_slots:
            if ms.material and ms.material.use_nodes:
                ensure_uv_orig(ms.material, orig_name)
        # per material_index bbox in original uv
        bbox = {}
        polys = {}
        for p in me.polygons:
            mi = p.material_index
            polys.setdefault(mi, []).append(p)
            for li in p.loop_indices:
                u, v = uvl.data[li].uv
                b = bbox.setdefault(mi, [1e18, 1e18, -1e18, -1e18])
                if u < b[0]: b[0] = u
                if v < b[1]: b[1] = v
                if u > b[2]: b[2] = u
                if v > b[3]: b[3] = v
        for mi in polys:
            groups.append({'ob': ob, 'mi': mi, 'polys': polys[mi], 'bbox': bbox[mi], 'orig': uvl, 'orig_name': orig_name})
    n = len(groups)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    rows = max(1, int(math.ceil(n / cols)))
    cw, ch = 1.0 / cols, 1.0 / rows
    pad = 0.04
    # create Atlas layer per mesh
    for ob in objs:
        me = ob.data
        if 'Atlas' in me.uv_layers:
            me.uv_layers.remove(me.uv_layers['Atlas'])
        me.uv_layers.new(name='Atlas')
    # assign atlas uvs sequentially into grid cells
    for gi, g in enumerate(groups):
        ob = g['ob']; me = ob.data
        atl = me.uv_layers['Atlas']
        col = gi % cols; row = gi // cols
        x0 = col * cw; y0 = row * ch
        b = g['bbox']
        du = max(1e-6, b[2] - b[0]); dv = max(1e-6, b[3] - b[1])
        for p in g['polys']:
            for li in p.loop_indices:
                u, v = g['orig'].data[li].uv
                au = x0 + pad * cw + (u - b[0]) / du * (cw * (1 - 2 * pad))
                av = y0 + pad * ch + (v - b[1]) / dv * (ch * (1 - 2 * pad))
                atl.data[li].uv = (au, av)
    # bake
    img = bpy.data.images.new('ATLAS_' + slot, RES, RES, alpha=True)
    img.colorspace_settings.name = 'sRGB'
    for ob in objs:
        for ms in ob.material_slots:
            if ms.material and ms.material.use_nodes:
                add_bake_target(ms.material, img)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.hide_render = False
        ob.hide_viewport = False
        try: ob.hide_set(False)
        except Exception: pass
        try: bpy.context.scene.collection.objects.link(ob)
        except Exception: pass
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    log('bake', slot, 'selected', len(bpy.context.selected_objects))
    _o = objs[0]
    _mats = 0
    for ms in _o.material_slots:
        if ms.material and ms.material.use_nodes:
            a = ms.material.node_tree.nodes.active
            if a is not None and a.type == 'TEX_IMAGE' and a.image is not None and a.select:
                _mats += 1
    log('DBG', _o.name, 'type', _o.type, 'mode', _o.mode, 'hide_get', _o.hide_get(),
        'hide_render', _o.hide_render, 'in_viewlayer', _o.name in bpy.context.view_layer.objects,
        'colls', [(c.name, c.hide_render, c.hide_viewport) for c in _o.users_collection],
        'valid_mat_nodes', _mats, 'uvs', [u.name for u in _o.data.uv_layers])
    # activate Atlas uv
    for ob in objs:
        me = ob.data
        me.uv_layers.active = me.uv_layers['Atlas']
        for lay in me.uv_layers:
            lay.active_render = (lay.name == 'Atlas')
    with bpy.context.temp_override(active_object=objs[0], object=objs[0],
                                   selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=4, use_clear=True)
    bake_alpha_into(img, objs, slot)
    p = os.path.join(OUT_TEX, slot + '.png')
    img.filepath_raw = p; img.file_format = 'PNG'; img.save()
    atlas_paths[slot] = p
    log('baked', slot, 'groups', n, '->', p)
    # finalize meshes: single material with atlas, keep only Atlas uv (renamed UVMap)
    for ob in objs:
        me = ob.data
        for s in list(me.materials):
            pass
        me.materials.clear()
        mat = bpy.data.materials.new(slot); mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get('Principled BSDF')
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
        nt.links.new(tx.outputs['Color'], bsdf.inputs['Base Color'])
        me.materials.append(mat)
        # uv: keep Atlas, drop others
        for layer in list(me.uv_layers):
            if layer.name != 'Atlas':
                me.uv_layers.remove(layer)
        me.uv_layers['Atlas'].name = 'UVMap'
        me.uv_layers.active = me.uv_layers['UVMap']

# ---- 4. export FBX ----
bpy.ops.object.select_all(action='DESELECT')
arm_obj.select_set(True)
for m in meshes: m.select_set(True)
bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.export_scene.fbx(filepath=OUT_FBX, use_selection=True, object_types={'ARMATURE','MESH'},
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
    add_leaf_bones=False, use_armature_deform_only=False, mesh_smooth_type='FACE',
    use_mesh_modifiers=False, bake_anim=False)
log('exported', OUT_FBX)
# dump image list for reference
imgs = [(i.name, tuple(i.size)) for i in bpy.data.images]
with open(os.path.join(OUT_TEX, '_images.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'name':n,'size':list(s)} for n,s in imgs], fh, ensure_ascii=False, indent=1)
log('DONE')


