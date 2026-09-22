# VideoImageOverlay v0.4.3 交接

## 当前状态

- 已完成现代浅色卡片 UI、适应窗口独立状态、连续 50%～400% 缩放、图片居中、鼠标锚点缩放、滑块同步、右键平移和拖动期间固定 4 倍放大镜。
- 选区仍使用全局归一化坐标；右键平移不会改变输出区域。
- 设置兼容 `fit`、`100%`、`150%`、`200%` 旧值迁移，非法值回退适应窗口。
- 已重制 `assets/app_icon.ico`，包含 16/32/48/64/128/256 六种尺寸。
- 首帧通过 `after_idle`、Configure 尺寸记录和 `_rendering_preview` 保护避免 1×1 渲染与递归。
- 常用素材卸载逐文件 SHA-256 比对；修改过的同名文件保留并记录日志。
- `build_release.ps1` 为已有脚本，本轮确认其使用仓库根路径、`build/work`、`build/spec` 和 `--distpath VideoImageOverlay`。

## 验证

- Python 单元/集成/GUI/素材测试：34 项通过；覆盖图片居中、鼠标锚点、BILINEAR/LANCZOS 分层渲染、80ms 定时器取消、4 倍放大镜和 Canvas 层级。
- 最终 EXE 在无系统 FFmpeg PATH 下使用 PyInstaller 内置组件处理带音频合成视频，输出成功，源视频 SHA-256 未变化。
- 最终 EXE：`VideoImageOverlay/VideoImageOverlay.exe`；SHA-256：`E5C4828FD9061EEFAC13017713289A61E773DDB5560845877EE5CDC251A5E2AD`。
- 放大预览仅在鼠标锚点路径调用 `update_idletasks()`：滚轮前读取实际画布坐标，重绘设置 `scrollregion` 后再次读取布局；主预览不执行该额外刷新。Tk Canvas 的滚动比例按 scrollregion 总尺寸计算，并对可滚动范围裁剪，避免缩放跳到左下角。

## 边界

用户目录 `素材/`、`替换图片/`、`成品/` 未修改、未暂存；未 push、未发布、未生成 ZIP。
- 交互缩放先使用 `Image.Resampling.BILINEAR`，新滚轮会 `after_cancel` 旧的 80ms 高质量定时器；停止后仅执行一次 `LANCZOS`。图片项、选区项和控制点复用，放大镜最后创建并 `tag_raise`，保证 z 顺序。
