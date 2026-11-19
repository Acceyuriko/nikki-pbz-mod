# Convert Nikki_2.0.blend into a clean rig + single skinned FBX for the pbz pipeline.
# Run: blender -b <Nikki_2.0.blend> -P nikki_export.py -- <out_fbx> <out_texdir>
import bpy, os, sys, json
from mathutils import Vector

argv = sys.argv[sys.argv.index('--')+1:]
OUT_FBX, OUT_TEX = argv[0], argv[1]
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

# clear parenting of meshes/armature but keep world transform
arm_obj.parent = None
for m in meshes:
    mw = m.matrix_world.copy(); m.parent = None; m.matrix_world = mw

# dump images (for later real-texture pass)
imgs = [(i.name, tuple(i.size)) for i in bpy.data.images]
log('images', len(imgs))
with open(os.path.join(OUT_TEX, '_images.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'name':n,'size':list(s)} for n,s in imgs], fh, ensure_ascii=False, indent=1)

# ---- 2. clean armature hierarchy ----
arm = arm_obj.data
weighted = set()
for m in meshes:
    for g in m.vertex_groups:
        if g.name in arm.bones:
            weighted.add(g.name)
log('weighted bones', len(weighted), 'of', len(arm.bones))

# key explicit parents
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
        base=f'{f}1.{s}'
        parent_map[base]=f'hand.{s}'

# anchors for nearest-parent of all other kept bones
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

kept = set(n for n in weighted if n in arm.bones)
# make sure chain bones needed for parenting are kept even if unweighted
for n in parent_map:
    if n in arm.bones: kept.add(n)
for n in anchor_names:
    if n in arm.bones: kept.add(n)

bpy.context.view_layer.objects.active = arm_obj
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.edit_bones
for b in eb: b.use_connect=False
# set parents for kept bones
for n in kept:
    if n not in eb: continue
    if n in parent_map:
        p = parent_map[n]
    else:
        p = nearest_anchor(arm.bones[n].head_local)
    if p and p in eb and p != n:
        eb[n].parent = eb[p]
    else:
        eb[n].parent = None
# delete non-kept bones (direct API; the operator only removed some in headless)
todo = [b.name for b in list(eb) if b.name not in kept]
log('removing bones', len(todo))
for n in todo:
    if n in eb:
        eb.remove(eb[n])

# guarantee a single root: re-attach any orphan bone to its nearest anchor
for b in list(eb):
    if b.parent is None and b.name != 'root.x':
        p = nearest_anchor(b.head)
        if p and p in eb and p != b.name:
            b.parent = eb[p]
        else:
            b.parent = eb['root.x']
orphans = [b.name for b in eb if b.parent is None]
log('roots now', orphans)

# sanitize bone names (dots/spaces -> _) while still in edit mode
import re as _re
ren = {}
existing = set(b.name for b in eb)
for b in list(eb):
    clean = _re.sub(r'[^A-Za-z0-9_]', '_', b.name)
    if clean != b.name and clean not in existing:
        ren[b.name] = clean
for old, new in ren.items():
    eb[old].name = new
bpy.ops.object.mode_set(mode='OBJECT')
for m in meshes:
    for g in m.vertex_groups:
        if g.name in ren: g.name = ren[g.name]
log('sanitize renamed', len(ren))
log('bones after clean', len(arm.bones))
for n in ['root.x','spine_01.x','spine_05.x','neck.x','head.x','shoulder.l','arm.l','forearm.l','hand.l','thigh.l','leg.l','foot.l','toes_01.l']:
    b=arm.bones.get(n)
    if b: log('BONE', n, 'parent', (b.parent.name if b.parent else None), 'head', tuple(round(v,3) for v in b.head_local))

# ---- 3. consolidate materials per mesh ----
def get_or_make(name, color):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name); mat.use_nodes=True
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf: bsdf.inputs['Base Color'].default_value=(color[0],color[1],color[2],1)
    return mat
COL = {'Skin':(0.95,0.80,0.70),'Face':(0.95,0.80,0.70),'Hair':(0.32,0.23,0.16),'Cloth':(0.93,0.86,0.89)}
mats = {k:get_or_make(k,v) for k,v in COL.items()}
for m in meshes:
    cat = CHARMESH.get(m.name,'Cloth')
    m.data.materials.clear()
    m.data.materials.append(mats[cat])
    for s in m.material_slots: s.material = mats[cat]

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

# ---- 5. solid color BC pngs ----
def solid(path, color, s=64):
    img = bpy.data.images.new(os.path.basename(path), s, s, alpha=True)
    px=[]
    for _ in range(s*s): px += [color[0],color[1],color[2],1.0]
    img.pixels.foreach_set(px)
    img.filepath_raw=path; img.file_format='PNG'; img.save(); bpy.data.images.remove(img)
    log('tex', path)
for k,c in COL.items():
    solid(os.path.join(OUT_TEX, f'{k}.png'), c)
log('DONE')
