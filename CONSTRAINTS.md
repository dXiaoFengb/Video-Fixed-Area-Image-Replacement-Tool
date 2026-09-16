# VideoImageOverlay 项目约束

- 只读输入：用户选择的源视频文件夹与所有外部资源库。不得删除、移动、改名、修改或覆盖源视频。
- 输出目标：仅用户选择的不同目标文件夹；同名结果必须递增编号，禁止覆盖已有文件。
- 媒体范围：只扫描源文件夹第一层；不递归；仅 CPU `libx264` 编码；不加入显卡编码或逐视频时间范围。
- 外部副作用：不发送消息、不上传数据、不运行生产任务、不改权限、不配置 Git 远程、不 push、不生成 ZIP、不发布 EXE。
- 构建目标：仅构建 `VideoImageOverlay/VideoImageOverlay.exe` 单文件；PyInstaller 临时产物只能写入 `VideoImageOverlay/build/`。
- Git：允许在本目录初始化本地仓库并提交源代码、文档和构建配置；`VideoImageOverlay.exe`、`settings.json`、`素材`、`替换图片`、`成品`、`build`、缓存和第三方下载素材不提交。

- 处理界面：批量处理期间仅更新日志、状态栏和汇总；FFmpeg/FFprobe 不得显示控制台窗口或读取交互输入。
