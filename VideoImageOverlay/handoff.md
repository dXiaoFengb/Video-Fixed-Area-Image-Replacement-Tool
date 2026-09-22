# VideoImageOverlay v0.4.1 交接

## 当前状态

- 已完成现代浅色卡片 UI、连续 50%～400% 缩放、右键平移和拖动期间固定 2.5 倍放大镜。
- 选区仍使用全局归一化坐标；右键平移不会改变输出区域。
- 设置兼容 `fit`、`100%`、`150%`、`200%` 旧值迁移，非法值回退适应窗口。
- 已重制 `assets/app_icon.ico`，包含 16/32/48/64/128/256 六种尺寸。
- 首帧通过 `after_idle`、Configure 尺寸记录和 `_rendering_preview` 保护避免 1×1 渲染与递归。
- 常用素材卸载逐文件 SHA-256 比对；修改过的同名文件保留并记录日志。
- `build_release.ps1` 为已有脚本，本轮确认其使用仓库根路径、`build/work`、`build/spec` 和 `--distpath VideoImageOverlay`。

## 验证

- Python 单元/集成/GUI/素材测试：29 项通过。
- 最终 EXE 在无系统 FFmpeg PATH 下使用 PyInstaller 内置组件处理带音频合成视频，输出成功，源视频 SHA-256 未变化。
- 最终 EXE：`VideoImageOverlay/VideoImageOverlay.exe`。

## 边界

用户目录 `素材/`、`替换图片/`、`成品/` 未修改、未暂存；未 push、未发布、未生成 ZIP。