# VideoImageOverlay

本目录包含 v0.1.0 源码、测试和构建脚本。`third_party/ffmpeg/` 仅保存构建时下载并校验的 FFmpeg/FFprobe，不纳入 Git；构建脚本通过 PyInstaller `--add-binary` 把它们嵌入单文件 EXE。

构建前将 `VideoImageOverlay/.build-tools` 加入 `PYTHONPATH`，再执行 `build_release.ps1`。最终程序运行时在 `sys._MEIPASS` 中定位内置媒体组件。
