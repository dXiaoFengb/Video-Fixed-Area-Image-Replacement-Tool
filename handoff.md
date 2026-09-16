# 交接与状态

> 下一个对话：先读 `AGENTS.md`、`TASK.md`、`CONSTRAINTS.md` 与本文件。

## 改动

- 创建 `VideoImageOverlay` Python/Tkinter 项目：首帧预览与选区、第一层视频扫描、全程图片覆盖、同名序号、取消/汇总、音频复制/AAC 回退与无界面验收入口。
- 添加 PyInstaller 单文件构建脚本，使用 `--add-binary` 内置 FFmpeg/FFprobe，并加入内置许可证。
- 将 README、TASK、CONSTRAINTS、VERSION 从模板更新为 v0.1.0 项目实际规则；新增测试与本地 Git 忽略规则。

## 验证

- `python -m unittest discover -s VideoImageOverlay\\tests -p test_*.py -v`：10/10 通过，覆盖序号、格式扫描、工具查找顺序、选区映射、图片覆盖像素、音频 AAC 回退和源码 GUI 构造。
- Release 单文件构建成功：`VideoImageOverlay/dist/VideoImageOverlay.exe`，105,736,399 字节；包体清单包含 `ffmpeg.exe`、`ffprobe.exe`、`FFMPEG-LICENSE.txt`。
- 干净 PATH（不含系统 FFmpeg）下，最终 EXE 的 `--batch` 验收成功：日志为“FFmpeg 来源：PyInstaller 内置组件”；输出 H.264/AAC MP4，源视频 SHA-256 未变化，并验证同名生成 `sample (1).mp4`。
- 正常启动最终 EXE 后观察到单文件引导/应用进程常驻，随后已停止测试进程。`--smoke-gui` 自动退出参数在冻结版 15 秒内超时，属未完成自动化验收，不影响已验证的正常启动或批处理。

## 状态

- 版本 / 代号：v0.1.0 / video-image-overlay。
- 发布：仅本地构建，未上传、未打包 ZIP、未发布远程；最终 EXE SHA-256 为 `3146EE6E7A99CB6EC79D1F247D8FE08DD890212B9FA2D77C37843FCB24A91DD9`。
- Git：本地 v0.1.0 初始提交；提交哈希以 `git rev-parse HEAD` 为准。不配置远程、不 push。

## 下一步

1. 初始化本地 Git，完成状态/空白检查后创建包含 `v0.1.0` 的首次提交。
2. 若需要完全自动化冻结版 GUI 回归，继续定位 `--smoke-gui` 在单文件 EXE 中未按时退出的原因。
