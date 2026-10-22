# DaVinci Tools — 达芬奇工具集

![version](https://img.shields.io/badge/version-v1.0.0-blue)
![platform](https://img.shields.io/badge/DaVinci%20Resolve-18%2B-orange)
![language](https://img.shields.io/badge/Lua%20%7C%20Python-3.8%2B-green)

一组基于 DaVinci Resolve 脚本 API（Lua / Python）开发的工作流工具，用于把剪辑中重复、繁琐的操作自动化。

## 工具清单

| 工具 | 目录 | 作用 |
|---|---|---|
| 音频自动分轨 | `DaVinci_Audio_Organizer` | 将当前时间线复制整理为配音、音乐、音效、同期原声及待确认轨，并设置片段颜色 |
| 当前帧截图 | `DaVinci_Frame_Capture` | 悬浮面板一键截取当前帧，可自选输出目录并自动记住 |

---

## 1. 达芬奇音频自动分轨

- **程序目录**：`DaVinci_Audio_Organizer`
- **启动方式**：达芬奇 → 工作区 → 脚本 → `Audio_Organizer`
- **功能**：将当前时间线复制整理为配音、音乐、音效、同期原声及待确认轨，并按轨类型设置片段颜色
- **分类规则**：`DaVinci_Audio_Organizer/rules.json`（可自行调整关键词与匹配规则）
- **详细说明**：`DaVinci_Audio_Organizer/使用说明.md`
- **备份与运行记录**：`DaVinci_Audio_Organizer/runs`（本机生成，不入库）

达芬奇菜单入口已更新为从此固定目录运行。原位置文件保留；正常使用不再依赖原来的日期文件夹。

## 2. 达芬奇当前帧截图

- **程序目录**：`DaVinci_Frame_Capture`
- **悬浮按钮**：达芬奇 → 工作区 → 脚本 → `Frame_Capture_Panel`
- **立即保存**：达芬奇 → 工作区 → 脚本 → `Frame_Capture_Now`
- **默认图片目录**：`DaVinci_Frame_Capture/Captures`
- 可以在悬浮窗里选择其他已有文件夹，后续会自动记住
- **详细说明**：`DaVinci_Frame_Capture/使用说明.md`

---

## 安装

1. 下载本仓库（`git clone` 或 Releases 里的源码包）
2. 将需要的工具目录放到达芬奇可访问的固定路径
3. 在达芬奇中打开 **工作区 → 脚本**，把 `.lua` 脚本放入脚本目录，或直接从菜单运行

> 详细步骤见各工具目录下的 `使用说明.md`。

## 版本

当前版本 **v1.0.0**，变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 目录说明

后续新增工具按"一工具一子文件夹"保存在仓库根目录，并更新本清单。

> 运行产物（`runs/`、`Captures/`）为本机生成数据，不入库；详见 `.gitignore`。
