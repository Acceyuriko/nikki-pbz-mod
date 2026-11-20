# -*- coding: utf-8 -*-
# 把 熠熠舞曲 blend 导出为「干净骨架 + 蒙皮」的 FBX，并把所有材质烘成 4 张图集贴图。
# 用法: blender -b <blend> -P export_wuyu.py -- <out_fbx> <out_texdir> [res]
import bpy, os, sys, math, json
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
BLEND, OUT_FBX, OUT_TEX = argv[0], argv[1], argv[2]
RES = int(argv[3]) if len(argv) > 3 else 2048
os.makedirs(os.path.dirname(OUT_FBX), exist_ok=True)
os.makedirs(OUT_TEX, exist_ok=True)
def log(*a): print('WUYU', *a, flush=True)

def alpha_source(mat):
    """返回材质的透明度来源：('link', from_socket) 或 ('const', 值)。
    优先取 BSDF Alpha 有连线的；否则取非 1 的常量；默认完全不透明 1。"""
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
    """把每个材质的不透明度烘成灰度图，再写进 color_img 的 alpha 通道。"""
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

bpy.ops.wm.open_mainfile(filepath=BLEND)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for o in bpy.data.objects:
    try: o.hide_set(False)
    except Exception: pass
    o.hide_viewport = False; o.hide_render = False
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()

def bound_meshes():
    return [o for o in bpy.data.objects if o.type == 'MESH'
            and any(m.type == 'ARMATURE' for m in o.modifiers)]

meshes = bound_meshes()
log('bound meshes', len(meshes), [o.name for o in meshes])

# 1) 按材质拆成单材质对象（方便每块单独归档到图集）
for o in list(meshes):
    if len(o.data.materials) <= 1:
        continue
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='MATERIAL')
    bpy.ops.object.mode_set(mode='OBJECT')

objs = [o for o in bound_meshes() if len(o.data.polygons) > 0]
log('after split', len(objs))

def slot_of(mat):
    n = (mat.name.split('.')[0] if mat else '')
    if n in ('Ground', 'Dots Stroke', ''):
        return None
    if n == 'MI_S0142H_01' or 'hair' in n.lower():
        return 'Hair'
    if any(k in n for k in ('Face', 'Eye', 'Cornea', 'Eyelash', 'Eyebrow', 'Brow')):
        return 'Face'
    if 'Body' in n or n == 'Skin':
        return 'Skin'
    return 'Cloth'   # 其余 S0142* / 羽毛 / 宝石 -> 衣服

slot_objs = {}
for o in objs:
    mat = o.data.materials[0] if len(o.data.materials) else None
    s = slot_of(mat)
    if s is None:
        continue
    slot_objs.setdefault(s, []).append(o)
log('slots', {k: len(v) for k, v in slot_objs.items()})

# 2) 烘焙设置
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = 1
sc.cycles.use_denoising = False
try: sc.cycles.device = 'CPU'
except Exception: pass
sc.render.bake.margin = 4
sc.render.bake.use_selected_to_active = False

def ensure_uv_orig(mat, uvname):
    nt = mat.node_tree
    uvn = nt.nodes.get('UV_ORIG')
    if uvn is None:
        uvn = nt.nodes.new('ShaderNodeUVMap'); uvn.uv_map = uvname; uvn.name = 'UV_ORIG'
    touched = set()
    for n in list(nt.nodes):
        if n.type != 'TEX_IMAGE':
            continue
        vec = n.inputs.get('Vector')
        if vec is None:
            continue
        if not vec.is_linked:
            nt.links.new(uvn.outputs['UV'], vec); continue
        src = vec.links[0].from_node
        if src.type == 'TEX_COORD':
            nt.links.new(uvn.outputs['UV'], vec)
        elif src.type == 'MAPPING' and id(src) not in touched:
            touched.add(id(src))
            mv = src.inputs.get('Vector')
            if mv is not None:
                nt.links.new(uvn.outputs['UV'], mv)

def add_bake_target(mat, img):
    nt = mat.node_tree
    tn = nt.nodes.get('BAKE_TARGET')
    if tn is None:
        tn = nt.nodes.new('ShaderNodeTexImage'); tn.name = 'BAKE_TARGET'
    tn.image = img
    for n in nt.nodes: n.select = False
    tn.select = True
    nt.nodes.active = tn

for slot, olist in slot_objs.items():
    n = len(olist)
    cols = max(1, int(math.ceil(math.sqrt(n)))); rows = max(1, int(math.ceil(n / cols)))
    cw, ch = 1.0 / cols, 1.0 / rows; pad = 0.04
    for o in olist:
        me = o.data
        if 'Atlas' in me.uv_layers:
            me.uv_layers.remove(me.uv_layers['Atlas'])
        orig = me.uv_layers.active
        atl = me.uv_layers.new(name='Atlas')
        u = min(0.0, 1.0); b = [1e18, 1e18, -1e18, -1e18]
        for p in me.polygons:
            for li in p.loop_indices:
                x, y = orig.data[li].uv
                b[0] = min(b[0], x); b[1] = min(b[1], y)
                b[2] = max(b[2], x); b[3] = max(b[3], y)
        # remember placement
        o['_atlas_bbox'] = b
    img = bpy.data.images.new('ATLAS_' + slot, RES, RES, alpha=True)
    img.colorspace_settings.name = 'sRGB'
    for gi, o in enumerate(olist):
        me = o.data
        orig = next(l for l in me.uv_layers if l.name != 'Atlas')
        atl = me.uv_layers['Atlas']
        col = gi % cols; row = gi // cols
        x0, y0 = col * cw, row * ch
        b = o['_atlas_bbox']
        du = max(1e-6, b[2] - b[0]); dv = max(1e-6, b[3] - b[1])
        for p in me.polygons:
            for li in p.loop_indices:
                x, y = orig.data[li].uv
                au = x0 + pad * cw + (x - b[0]) / du * (cw * (1 - 2 * pad))
                av = y0 + pad * ch + (y - b[1]) / dv * (ch * (1 - 2 * pad))
                atl.data[li].uv = (au, av)
        for ms in o.material_slots:
            if ms.material and ms.material.use_nodes:
                ensure_uv_orig(ms.material, orig.name)
                add_bake_target(ms.material, img)
        me.uv_layers.active = atl
        for l in me.uv_layers:
            l.active_render = (l.name == 'Atlas')
    bpy.ops.object.select_all(action='DESELECT')
    for o in olist:
        o.hide_set(False); o.hide_viewport = False; o.hide_render = False
        try: bpy.context.scene.collection.objects.link(o)
        except Exception: pass
        o.select_set(True)
    bpy.context.view_layer.objects.active = olist[0]
    log('bake', slot, 'objects', len(olist))
    with bpy.context.temp_override(active_object=olist[0], object=olist[0],
                                   selected_objects=olist, selected_editable_objects=olist):
        bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=4, use_clear=True)
    bake_alpha_into(img, olist, slot)
    p = os.path.join(OUT_TEX, slot + '.png')
    img.filepath_raw = p; img.file_format = 'PNG'; img.save()
    log('baked', slot, '->', p)
    # 换材质
    mat = bpy.data.materials.new(slot); mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
    nt.links.new(tx.outputs['Color'], bsdf.inputs['Base Color'])
    for o in olist:
        me = o.data
        me.materials.clear(); me.materials.append(mat)
        for l in list(me.uv_layers):
            if l.name != 'Atlas':
                me.uv_layers.remove(l)
        me.uv_layers['Atlas'].name = 'UVMap'
        me.uv_layers.active = me.uv_layers['UVMap']
    for o in olist:
        if '_atlas_bbox' in o:
            del o['_atlas_bbox']

# 3) 导出（保持父子关系；骨架必须在视口可见，否则 FBX 不会导出骨架）
keep = [o for sl in slot_objs.values() for o in sl]
bpy.ops.object.select_all(action='DESELECT')
arm.hide_set(False)
arm.select_set(True)
for o in keep:
    o.hide_set(False); o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.export_scene.fbx(filepath=OUT_FBX, use_selection=True, object_types={'ARMATURE', 'MESH'},
    apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
    add_leaf_bones=False, use_armature_deform_only=False, mesh_smooth_type='FACE',
    use_mesh_modifiers=False, bake_anim=False)
log('exported', OUT_FBX)
log('DONE')
