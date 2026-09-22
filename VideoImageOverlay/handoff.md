# VideoImageOverlay v0.4.2 交接

## 当前状态

- 已完成现代浅色卡片 UI、适应窗口独立状态、连续 50%～400% 缩放、鼠标锚点缩放、滑块同步、右键平移和拖动期间固定 2.5 倍放大镜。
- 选区仍使用全局归一化坐标；右键平移不会改变输出区域。
- 设置兼容 `fit`、`100%`、`150%`、`200%` 旧值迁移，非法值回退适应窗口。
- 已重制 `assets/app_icon.ico`，包含 16/32/48/64/128/256 六种尺寸。
- 首帧通过 `after_idle`、Configure 尺寸记录和 `_rendering_preview` 保护避免 1×1 渲染与递归。
- 常用素材卸载逐文件 SHA-256 比对；修改过的同名文件保留并记录日志。
- `build_release.ps1` 为已有脚本，本轮确认其使用仓库根路径、`build/work`、`build/spec` 和 `--distpath VideoImageOverlay`。

## 验证

- Python 单元/集成/GUI/素材测试：31 项通过；新增已平移视图锚点稳定、滑块同步和适应窗口状态测试。
- 最终 EXE 在无系统 FFmpeg PATH 下使用 PyInstaller 内置组件处理带音频合成视频，输出成功，源视频 SHA-256 未变化。
- 最终 EXE：`VideoImageOverlay/VideoImageOverlay.exe`；SHA-256：`0E3E96592BDACB085689C5A8D007D7585C82DE07056CF44C1C5CC071FDCBDDEE`。
- 放大预览仅在鼠标锚点路径调用 `update_idletasks()`：滚轮前读取实际画布坐标，重绘设置 `scrollregion` 后再次读取布局；主预览不执行该额外刷新。Tk Canvas 的滚动比例按 scrollregion 总尺寸计算，并对可滚动范围裁剪，避免缩放跳到左下角。

## 边界

用户目录 `素材/`、`替换图片/`、`成品/` 未修改、未暂存；未 push、未发布、未生成 ZIP。