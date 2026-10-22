# DaVinci Tools — 达芬奇工具集

一组基于 DaVinci Resolve 脚本 API（Lua / Python）开发的工作流工具。

## 达芬奇音频自动分轨

- 程序目录：DaVinci_Audio_Organizer
- 使用：达芬奇 → 工作区 → 脚本 → Audio_Organizer
- 功能：将当前时间线复制整理为配音、音乐、音效、同期原声及待确认轨，并设置片段颜色。
- 分类规则：DaVinci_Audio_Organizer\rules.json
- 详细说明：DaVinci_Audio_Organizer\使用说明.md
- 备份与运行记录：DaVinci_Audio_Organizer\runs

达芬奇菜单入口已更新为从此固定目录运行。原位置文件保留；正常使用不再依赖原来的日期文件夹。

后续新增工具按“一工具一子文件夹”保存在此目录，并更新本清单。

> 运行产物（`runs/`、`Captures/`）为本机生成数据，不入库；详见 `.gitignore`。
## 达芬奇当前帧截图

- 程序目录：DaVinci_Frame_Capture
- 悬浮按钮：达芬奇 → 工作区 → 脚本 → Frame_Capture_Panel
- 立即保存：达芬奇 → 工作区 → 脚本 → Frame_Capture_Now
- 默认图片目录：DaVinci_Frame_Capture\Captures
- 可以在悬浮窗里选择其他已有文件夹，后续会自动记住。
- 详细说明：DaVinci_Frame_Capture\使用说明.md