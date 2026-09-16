# 当前任务：VideoImageOverlay v0.2.0

## 目标

构建可直接运行的 v0.2.0 便携 EXE，保存最近路径、选区和窗口状态，并在无弹窗媒体处理下批量输出视频。

## 边界

- 允许修改：本项目根目录中的文档、`VideoImageOverlay` 源码、测试、构建配置与本地 Git 元数据。
- 禁止：修改源视频、递归处理子文件夹、修改外部资源库、使用显卡编码、逐视频设置时间段、上传、远程发布、ZIP、Git push 或远程配置。
- 需再次确认：替换已有用户文件、外部发布、权限变更、外部资源库修改。

## 验收标准

- 单文件 EXE 经 PyInstaller `--add-binary` 内置 FFmpeg 与 FFprobe，并在无系统 FFmpeg 环境成功处理合成视频。
- 支持指定扩展名、同名自动序号、首帧预览与框选、全程覆盖、音频复制/AAC 回退、取消和结果汇总。
- 已完成持久化、无窗口媒体调用、单元、集成与 GUI 回归验证；最终交付物仅为 `VideoImageOverlay/VideoImageOverlay.exe`。

> 执行状态与证据写在 `handoff.md`。
