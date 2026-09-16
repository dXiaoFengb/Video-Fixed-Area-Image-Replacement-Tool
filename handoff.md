# 交接与状态

> 下一个对话：先读 `AGENTS.md`、`TASK.md`、`CONSTRAINTS.md` 与本文件。

## 改动

- v0.2.0 新增同目录便携 `settings.json`：保存源/目标/图片路径、归一化选区、位置模式和窗口状态，并通过临时文件与原子替换写入。
- 启动恢复有效源路径的首帧与选区；失效路径仅显示并写日志。FFmpeg/FFprobe 统一禁用交互输入，Windows 下隐藏子进程窗口；处理期不弹模态窗口。
- PyInstaller 中间产物改在 `VideoImageOverlay/build/`，最终单文件交付物改为 `VideoImageOverlay/VideoImageOverlay.exe`。
- `.gitignore` 排除最终 EXE、settings、build、测试临时文件及用户的素材/替换图片/成品目录。

## 验证

- `python -m unittest discover -s VideoImageOverlay\tests -p test_*.py -v`：17/17 通过，涵盖既有扫描、序号、音频、覆盖、取消和 GUI 回归，以及 settings 读写/损坏回退/原子替换、冻结/开发基准、选区跨分辨率恢复、隐藏窗口与非交互调用。
- 最终 `VideoImageOverlay/VideoImageOverlay.exe` 在无系统 FFmpeg PATH 下成功处理合成视频；日志确认“FFmpeg 来源：PyInstaller 内置组件”，输出为 H.264/AAC MP4，源视频 SHA-256 未变化。

## 状态

- 版本 / 代号：v0.2.0 / portable-state。
- 发布：仅本地构建，未上传、未生成 ZIP、未发布远程；`VideoImageOverlay/VideoImageOverlay.exe` SHA-256：`DF5F498EC4637F0334C6F8AD14E475A131259AAA041127D20DDF97EDDCFBCA80`。
- Git：仓库根为 `E:\Ai\Ai\视频自动剪辑`；已创建本地 v0.2.0 提交 `02c5b088b9b9aaf8c045e7551b3d9f20ec267a25`；无远程配置、未 push。

## 下一步

1. 如需人工视觉验收，可在目标 Windows 设备选择真实素材路径，检查恢复的窗口状态、预览和选区位置。