# 影之刃零 · 暖暖（Nikki）替换魂 mod

把《影之刃零》（Phantom Blade Zero）主角「魂」的模型换成「暖暖 Nikki」。

- 📥 下载 / Download：[Nexus Mods 页面](https://www.nexusmods.com/phantombladezero/mods/1362)
- 游戏：Phantom Blade Zero（UE 5.7，Steam build 26367565）
- 替换对象：主角魂
- 版本：default-phys（带次级物理）

## 效果

- 进游戏后，有魂的场景都会显示暖暖。
- 动作从魂重定向到暖暖，手部做了 IK 对齐。
- 衣服和头发有基础物理摆动。

## 安装

1. 先关掉游戏。
2. 下载 `zzz_Nikki_P.pak`、`zzz_Nikki_P.ucas`、`zzz_Nikki_P.utoc` 三个文件。
3. 复制到游戏的 mod 目录：
   `...\PBZ\ProjectPBZ\Content\Paks\~mods\`
4. 启动游戏。

一次只放这一个 mod，不要和别的替换 mod 混用。

## 卸载

把上面 3 个文件从 `~mods` 删掉即可。

## 构建

本仓库只放 mod 配置和脚本，**不含模型原始贴图和 FBX**（版权原因，需自备）。

构建依赖通用工具链 `yzr-zero-mod`：
https://github.com/627157746/yzr-zero-mod

步骤：

1. 把 `mod.json` 和本目录的 `.py` 脚本放进工具链的 `mods/nikki/`。
2. 把暖暖模型 `Nikki_2.0.blend` 放进 `mods/nikki/`。
3. 用 Blender 跑 `export_fbx_real.py` 生成 `input/fbx/Nikki.fbx` 和 `input/textures/*.png`。
4. 运行 `pwsh tools\build-mod.ps1 -Mod nikki` 出包。

构建笔记见 [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md)。

## 文件

- `mod.json`：mod 的全部配置（材质槽、重定向链、次级物理分组、碰撞对）。
- `export_fbx_real.py`：从 `.blend` 烘焙真实贴图并导出 FBX。
- `export_fbx.py`：纯色版导出。
- `wgfix.py`：蒙皮权重修正（手臂、裙子）。
- `docs/安装说明.md`：给玩家的安装说明。
- `docs/BUILD_NOTES.md`：构建过程笔记。

## 说明

- 模型和贴图来自「无限暖暖 Infinity Nikki」官方资源，版权归原公司所有。本仓库不提供这些资产，仅共享 mod 配置与处理脚本，请勿用于商业用途。
- 本 mod 仅供个人学习与游戏娱乐使用。
