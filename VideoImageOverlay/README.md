# VideoImageOverlay v0.2.0

本目录包含源码、测试和构建脚本。用户的 `素材`、`替换图片`、`成品` 均保留在本目录，既不移动也不纳入 Git。

构建脚本将 PyInstaller 的工作目录与 spec 文件放入 `build/`，并把单文件交付物输出为同目录的 `VideoImageOverlay.exe`。FFmpeg、FFprobe 与许可证通过 `--add-binary`/`--add-data` 内置到 EXE。

`settings.json` 与 EXE 同目录，采用原子写入保存最近路径、归一化选区和窗口状态；它包含本机路径，已被 Git 忽略。