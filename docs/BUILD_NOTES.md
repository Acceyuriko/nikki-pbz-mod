# nikki mod —— 构建笔记

把暖暖（Nikki）模型换成影之刃零的魂。工具链：`C:\Users\zec_i\Documents\tmp\yzr-zero-mod`。

## 两条转换路线

- `export_fbx.py`：纯色版（第一版，已验证）。四个材质槽 Skin/Face/Hair/Cloth 用纯色 PNG。
  产物已验证、可出包。备份在 `mods/nikki/release_v1_flat/`。

- `export_fbx_real.py`：真实贴图版（第二版）。把原 blend 里每个（网格+材质）分组的漫反射颜色
  烘进对应槽的一张图集，再导出。
  命令：`blender -b Nikki_2.0.blend -P export_fbx_real.py -- <out_fbx> <out_tex> [分辨率]`
  - 原理：给每个分组在原 UV 里算包围盒，映射到该槽图集的一个互不重叠格子（网格×材质分组数决定 网格）。
  - 贴图读取走 `UV_ORIG`（UVMap 节点指向原 UV），烘焙写入 `Atlas`（active_render）。
    注意：原 blend 的 `render.bake.use_selected_to_active` 是 True，必须先设 False，否则报
    "No valid selected objects"。
  - 材质读原贴图；烘焙 pass 用 `DIFFUSE` + `pass_filter={'COLOR'}`，samples=1。
  - 烘完把网格材质换成单一「图集贴图」材质，只保留 Atlas UV（改名 UVMap）。

## 构建（出包）

1. 生成 FBX + 贴图（上面 export_fbx_real 或 export_fbx）。
2. 保证 mod.json 的 textures[].source 指向 input/textures/{Skin,Face,Hair,Cloth}.png。
3. 设 .NET10 运行时给 verify 用：
   `$env:DOTNET_ROOT='C:\Users\zec_i\dotnet10'`，PATH 前置它。
4. `pwsh -NoProfile -File tools\build-mod.ps1 -Mod nikki -NoPhys`
   （-NoPhys 先不烘物理，稳定后再开物理。）
5. 产物在 `mods/nikki/release/default-basic/.../~mods/`，`verify_release.py` 全绿。

## 依赖的原生库（verify 用）

放在 `C:\tools\CUE4Parse\runtime\`：
- `zlib-ng2.dll`：NotOfficer/Zlib-ng.NET release 1.0.0
- `oodle-data-shared.dll`：WorkingRobot/OodleUE clang-cl-x64-release.zip 的 bin 里取

## 已知问题 / 下一步

- 真实贴图版是漫反射颜色烘焙，不含法线/高光细节；衣服飘带、头发物理未做。
- 图集是等分网格，长条部件浪费空间；更高分辨率（2048/4096）更清晰，但烘焙更慢。
- 若游戏里颜色偏暗/偏亮，多半是游戏 MI 的 shader 参数，需要再调 BC 或换漫反射强度。

## 物理摆动（2026-11-19）

- 物理关键在骨架：布料/头发/飘带骨必须保留原始父子链（export_fbx_real.py 第2步优先用原父骨，找不到保留祖先才就近挂躯干/头）。压平成直挂躯干会让链条断掉、物理摆不起来。
- mod.json 的 physics 段按本模型骨骼名配 groups：skirt=`^c_skirt_0[1-6]_0[1-3]_[lr]$`、underskirt=`^NP_Cloth_Part03_`、ribbon=`^NP_Cloth_Part04_`（长飘带）、hair=`(?i)hair`。碰撞体 leg/spine/head，collide_pairs=[[skirt,leg],[ribbon,leg]]。
- 出包：`pwsh tools\build-mod.ps1 -Mod nikki`（**不带** -NoPhys）→ 变体 default-phys，生成 PA_Nikki_Secondary，verify 会检查到它。ucas 约 20.4MB。
- Blender 预览看不出物理，必须在游戏里走动/攻击验证。物理参数照 ciel/wendy 的 mod.json 比例配，抖得厉害就调 stiff/swing，穿模就加 collide_pairs。

## 第二套：熠熠舞曲（2026-11-19）

- 素材来源：B站 Airsoya 的 Blender 工程 `Nikki熠熠舞曲_5.0_B2.blend`。自带完整骨架 299 根骨头（Spine1_M / Shoulder_L / Hip_L / NP_Cloth_Part01_* / NP_Hair_Part01_* 这种命名），贴图全部打包在 blend 里。
- 导出脚本 `wuyu/export_wuyu.py`，和第一套 `export_fbx_real.py` 的思路一样，但有两处不同：
  1. 按材质拆网格（`bpy.ops.mesh.separate(type='MATERIAL')`）再分组，因为这套模型一个网格里混了身体/脸/眼睛/裙子多种材质，不能按网格分槽。
  2. 槽位按材质名判断：含 Face/Eye/Cornea/Eyelash/Eyebrow/Brow → Face；`MI_S0142H_01` 或 hair → Hair；含 Body → Skin；其余 `MI_S0142*` 和羽毛/宝石 → Cloth。
- 骨架在 blend 里是隐藏的（`hide_get()==True`），FBX 导出会跳过隐藏的骨架。导出前必须 `arm.hide_set(False)`，否则导出的 FBX 只有网格没有骨架。
- 这套不用 `adapt_humanoid`，走纯 IK 重定向，和第一套一样。`retarget.chains` 填新骨骼名：Spine=[Spine1_M,Chest_Mid_M]、LeftArm=[Shoulder_L,Wrist_L]、LeftLeg=[Hip_L,Ankle_L]、LeftClavicle=[Scapula_L,Scapula_L]，手指用 `XxxFinger1_L..3_L` 三段链。`root_bone` 用 `Root`。
- 物理：裙子骨头 `^NP_Cloth_Part01_`（34 个刚体）、头发 `(?i)hair`（16 个刚体）。**collide_pairs 留空**——长拖尾加碰撞会炸，用户要求让它穿模。kinematic_colliders 也留空。
- 出包：`pwsh tools\build-mod.ps1 -Mod nikki-wuyu` → `release/default-phys`，`zzz_NikkiWuyu_P.ucas` 约 32.5MB（2048 图集比第一套大）。verify 全绿。
- 隐患：宝石/羽毛是透明和自发光的材质，烘 DIFFUSE 颜色时变成黑色块，游戏里这部分会偏暗或发黑。
