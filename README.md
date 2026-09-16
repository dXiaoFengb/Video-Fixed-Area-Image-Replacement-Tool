# 视频固定区域图片替换工具

`VideoImageOverlay` 是本地 Windows 桌面程序：选择源视频文件夹、目标文件夹和图片，在首帧预览中框选区域后，批量生成覆盖该区域的 H.264 MP4。

## 项目档案

- 项目名称 / 定位：VideoImageOverlay，本地离线批量视频图片覆盖工具。
- 技术栈：Python 3.11、Tkinter、Pillow、FFmpeg 9.0.1 essentials、PyInstaller。
- 源码：`VideoImageOverlay/video_image_overlay/`；测试：`VideoImageOverlay/tests/`；产物：`VideoImageOverlay/dist/`。
- 构建：在 `VideoImageOverlay` 内执行 `powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Clean`。
- 测试：设置 `PYTHONPATH=VideoImageOverlay` 后运行 `python -m unittest discover -s VideoImageOverlay\tests -v`。
- 发布路径：仅本地 `VideoImageOverlay/dist/VideoImageOverlay.exe`；不上传、不打包 ZIP、不发布远程。
- 只读输入：用户选择的源视频文件夹和外部资源库。
- 版本规则：见 `VERSION.md`，当前固定为 `v0.1.0`。

## 使用方式

1. 选择源文件夹、与其不同的目标文件夹和替换图片。
2. 程序从源文件夹第一层找到首个支持的视频并显示首帧。
3. 拖拽创建选区；拖动选区内部可移动，拖动右下角可缩放。
4. 点击“开始批量处理”。程序将图片等比裁剪铺满选区，输出同名 MP4；冲突时自动追加序号。

程序优先从 EXE 同目录查找 FFmpeg/FFprobe，再使用 PyInstaller 内置组件，最后才回退系统 PATH；实际来源会写入日志。
