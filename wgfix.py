# -*- coding: utf-8 -*-
# Rebinding helper for cloth meshes whose skirt is wrongly skinned to arm bones.
#
# Two different things are fixed here:
#  A) dress (the bodice + the big bell sleeves):
#     - vertices that really are sleeve cloth (physically wrapped around an arm bone)
#       are re-bound to the DRIVABLE arm chain (shoulder/arm/forearm/hand .l/.r),
#       because the source rig spreads sleeve weights over many extra arm bones
#       (Shoulder_R, arm_ik, arm_twist_2, arm_stretch ...) that the retarget never
#       animates -> the sleeve would stay behind when the arm moves.
#     - vertices on the skirt/bodice that only have stray arm weight are stripped of
#       it (and re-bound to torso/skirt if too little weight is left).
#  B) other cloth meshes (dress.001, choker, neckwear): just strip arm weights.
import re

ARM_KW = ('shoulder', 'arm', 'forearm', 'hand', 'wrist', 'elbow',
          'thumb', 'index', 'middle', 'ring', 'pinky', 'scapula', 'clavicle', 'c_hand')

def is_arm(name):
    ln = name.lower()
    if 'armwing' in ln:
        return False
    return any(k in ln for k in ARM_KW)

def _dist2_seg(p, a, b):
    ab = b - a
    L2 = ab.length_squared
    if L2 < 1e-12:
        return (p - a).length_squared
    t = (p - a).dot(ab) / L2
    t = max(0.0, min(1.0, t))
    proj = a + ab * t
    return (p - proj).length_squared

CANON = ('shoulder.l', 'arm.l', 'forearm.l', 'hand.l',
         'shoulder.r', 'arm.r', 'forearm.r', 'hand.r')

CANON_SET = set(CANON)
FING_KW = ('thumb', 'index', 'middle', 'ring', 'pinky')

def _is_extra_arm(name):
    # an arm bone that the retarget never animates (stretch/twist/ik/elbow/shoulder
    # helper bones from the source rig), but NOT the canonical chain and NOT fingers.
    if not is_arm(name):
        return False
    if name in CANON_SET:
        return False
    ln = name.lower()
    if any(k in ln for k in FING_KW):
        return False
    return True

def fix_body_arm(bpy, arm_obj, meshes, log):
    # The bare arm skin (and sleeve accessory meshes) is weighted to the source rig's
    # redundant arm bones (arm_stretch, forearm_stretch, forearm_twist, arm_twist_2,
    # c_arm_twist_offset, shoulder_deform ...). Those bones are NOT driven by the
    # retarget, so when the arm bends the skin tears at the elbow. Rebind each arm-region
    # vertex's weight from those extra bones onto the drivable canonical chain
    # (shoulder/arm/forearm/hand .l/.r), by nearest bone segment.
    arm = arm_obj.data
    bone_names = set(b.name for b in arm.bones)
    aw = arm_obj.matrix_world
    canon = []
    for nm in CANON:
        b = arm.bones.get(nm)
        if b:
            canon.append((nm, aw @ b.head_local, aw @ b.tail_local))
    log('body-arm canon', [c[0] for c in canon])
    RAD2 = 0.12 * 0.12   # 12 cm
    for mesh in meshes:
        mw = mesh.matrix_world
        idx2name = {g.index: g.name for g in mesh.vertex_groups}
        vg = {g.name: g for g in mesh.vertex_groups}
        def ensure(n):
            g = vg.get(n)
            if g is None:
                g = mesh.vertex_groups.new(name=n)
                vg[n] = g
            return g
        n_fix = 0
        for v in mesh.data.vertices:
            cur = {}
            for ge in v.groups:
                n = idx2name.get(ge.group)
                if n is not None and n in bone_names:
                    cur[n] = ge.weight
            if not cur:
                continue
            dom = max(cur.items(), key=lambda x: x[1])[0]
            if not is_arm(dom):
                continue
            armw = {n: w for n, w in cur.items() if is_arm(n)}
            if sum(armw.values()) < 0.5:
                continue
            p = mw @ v.co
            dd = sorted((_dist2_seg(p, h, t), nm) for nm, h, t in canon)
            if dd[0][0] > RAD2:
                continue
            extra = {n: w for n, w in armw.items() if _is_extra_arm(n)}
            exsum = sum(extra.values())
            if exsum <= 0.0:
                continue
            for n in extra:
                vg[n].remove([v.index])
            order = dd[:2]
            ws = [(nm, 1.0 / (dist + 1e-9)) for dist, nm in order]
            s = sum(w for _, w in ws)
            for nm, w in ws:
                ensure(nm).add([v.index], exsum * w / s, 'ADD')
            n_fix += 1
        log(f'body-arm-fix {mesh.name}: remapped={n_fix}')
    return True

def fix_skirt_rigid(bpy, arm_obj, meshes, log):
    # The outer skirt layers are skinned to 'root.x' in the source, so they are rigid
    # and the legs poke through them when running. The rig already HAS a whole skirt
    # physics chain (c_skirt_01..06 x _01..03 x l/r, 3 rings around the skirt). Rebind
    # every root-driven skirt vertex onto the nearest 2 c_skirt bones so the engine's
    # skirt physics + leg colliders drive it (only affects verts whose dominant bone is
    # root.x and that sit close to a c_skirt bone -> other root cloth untouched).
    arm = arm_obj.data
    bone_names = set(b.name for b in arm.bones)
    aw = arm_obj.matrix_world
    cseg = []
    for b in arm.bones:
        if re.match(r'^c_skirt_', b.name):
            cseg.append((b.name, aw @ b.head_local, aw @ b.tail_local))
    log('skirt-rigid c_skirt bones', len(cseg))
    RAD2 = 0.22 * 0.22
    for mesh in meshes:
        mw = mesh.matrix_world
        idx2name = {g.index: g.name for g in mesh.vertex_groups}
        vg = {g.name: g for g in mesh.vertex_groups}
        def ensure(n):
            g = vg.get(n)
            if g is None:
                g = mesh.vertex_groups.new(name=n); vg[n] = g
            return g
        n_fix = 0
        for v in mesh.data.vertices:
            cur = {}
            for ge in v.groups:
                n = idx2name.get(ge.group)
                if n is not None and n in bone_names:
                    cur[n] = ge.weight
            if not cur:
                continue
            dom = max(cur.items(), key=lambda x: x[1])[0]
            if dom not in ('root.x', 'root_x'):
                continue
            p = mw @ v.co
            dd = sorted((_dist2_seg(p, h, t), nm) for nm, h, t in cseg)
            if not dd or dd[0][0] > RAD2:
                continue
            for n in list(cur):
                vg[n].remove([v.index])
            order = dd[:2]
            ws = [(nm, 1.0 / (dist + 1e-9)) for dist, nm in order]
            s = sum(w for _, w in ws)
            for nm, w in ws:
                ensure(nm).add([v.index], w / s, 'REPLACE')
            n_fix += 1
        log(f'skirt-rigid fix {mesh.name}: rebind={n_fix}')
    return True

def apply(bpy, arm_obj, meshes, log):
    arm = arm_obj.data
    bone_names = set(b.name for b in arm.bones)
    aw = arm_obj.matrix_world
    # safe bones: real, non-arm, torso/pelvis/skirt deformers
    safe = []
    for b in arm.bones:
        if is_arm(b.name):
            continue
        ln = b.name.lower()
        if ln.startswith('c_skirt') or ln.startswith('spine_') or b.name == 'root.x':
            safe.append((b.name, aw @ b.head_local, aw @ b.tail_local))
    # canonical drivable arm chain (the bones the retarget actually animates)
    canon = []
    for nm in CANON:
        b = arm.bones.get(nm)
        if b:
            canon.append((nm, aw @ b.head_local, aw @ b.tail_local))
    log('weight-fix safe bones', len(safe), 'canon arm', [c[0] for c in canon])
    for mesh in meshes:
        mw = mesh.matrix_world
        idx2name = {g.index: g.name for g in mesh.vertex_groups}
        vg = {g.name: g for g in mesh.vertex_groups}
        def ensure(n):
            g = vg.get(n)
            if g is None:
                g = mesh.vertex_groups.new(name=n)
                vg[n] = g
            return g
        n_keep = n_rebind = n_sleeve = 0
        for v in mesh.data.vertices:
            cur = {}
            for ge in v.groups:
                n = idx2name.get(ge.group)
                if n is not None and n in bone_names:
                    cur[n] = ge.weight
            armw = {n: w for n, w in cur.items() if is_arm(n)}
            nonarm = {n: w for n, w in cur.items() if not is_arm(n)}
            if not armw:
                continue
            dom = max(cur.items(), key=lambda x: x[1])[0]
            if mesh.name == 'dress' and is_arm(dom):
                # Genuine sleeve cloth: the ORIGINAL dominant bone is an arm bone
                # (hand/forearm_twist/c_arm_twist_offset/...). The whole sleeve panel
                # in the source is arm-driven; keep it on the drivable arm chain and
                # never move it onto skirt/body (that split is what tore the panel).
                p = mw @ v.co
                remArm = sum(armw.values())
                for n in armw:
                    vg[n].remove([v.index])
                # keep the two nearest canonical (drivable) arm bones
                order = sorted(((_dist2_seg(p, h, t), nm) for nm, h, t in canon))[:2]
                ws = [(nm, 1.0 / (dist + 1e-6)) for dist, nm in order]
                s = sum(w for _, w in ws)
                for nm, w in ws:
                    ensure(nm).add([v.index], remArm * w / s, 'ADD')
                n_sleeve += 1
                continue
            # otherwise: strip arm weight; keep non-arm if enough, else rebind to safe
            sumR = sum(nonarm.values())
            for n in armw:
                vg[n].remove([v.index])
            if sumR >= 0.5:
                for n, w in nonarm.items():
                    vg[n].add([v.index], w / sumR, 'REPLACE')
                n_keep += 1
            else:
                for n in nonarm:
                    vg[n].remove([v.index])
                p = mw @ v.co
                d = sorted((_dist2_seg(p, h, t), nm) for nm, h, t in safe)[:3]
                ws = [(nm, 1.0 / (dist + 1e-6)) for dist, nm in d]
                s = sum(w for _, w in ws)
                for nm, w in ws:
                    ensure(nm).add([v.index], w / s, 'REPLACE')
                n_rebind += 1
        log(f'weight-fix {mesh.name}: sleeve={n_sleeve} keep={n_keep} rebind={n_rebind}')
    return True
