# 更新记录

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## v1.0.0 — 2026-10-22

首个正式版本。

### 新增

- **达芬奇音频自动分轨**（`DaVinci_Audio_Organizer`）
  - 通过达芬奇脚本菜单一键运行，无需外部脚本权限
  - 自动将时间线复制整理为配音、音乐、音效、同期原声、待确认轨
  - 按轨类型设置片段颜色，输出分类报告（CSV / JSON）
  - 支持自定义分类规则（`rules.json`）
  - 运行前自动备份 `.drt`，运行记录保存在 `runs/`
  - 附带 Python 单元测试（`test_audio_organizer.py`）
  - 限制：v1 仅支持纯单声道或纯立体声时间线，暂不支持单声道/立体声混合时间线自动分轨

- **达芬奇当前帧截图**（`DaVinci_Frame_Capture`）
  - `Frame_Capture_Panel`：悬浮面板，一键截取当前帧
  - `Frame_Capture_Now`：菜单直接截图
  - 输出目录可在面板内选择，选择结果自动记住

### 说明

- 仓库首版，运行产物（`runs/`、`Captures/`）已通过 `.gitignore` 排除
