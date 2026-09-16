from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .engine import Region, ToolResolver, VideoProcessor, extract_first_frame, scan_videos, temporary_frame_path
from .gui_math import PreviewGeometry


class VideoImageOverlayApp(ttk.Frame):
    CANVAS_WIDTH = 760
    CANVAS_HEIGHT = 428

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=12)
        self.root = root
        self.root.title("VideoImageOverlay v0.1.0")
        self.root.minsize(920, 760)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.image_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请选择源文件夹、目标文件夹和替换图片。")
        self.progress_var = tk.DoubleVar(value=0)
        self.preview_geometry: PreviewGeometry | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.drag_mode: str | None = None
        self.drag_anchor = (0.0, 0.0)
        self.rectangle = [170.0, 100.0, 390.0, 220.0]
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.processor: VideoProcessor | None = None
        self._build()

    def _build(self) -> None:
        form = ttk.LabelFrame(self, text="输入与输出", padding=8)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        for row, (label, variable, action) in enumerate((("源文件夹", self.source_var, self.choose_source), ("目标文件夹", self.destination_var, self.choose_destination), ("替换图片", self.image_var, self.choose_image))):
            ttk.Label(form, text=label).grid(row=row, column=0, padx=(0, 8), pady=4, sticky="w")
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, pady=4, sticky="ew")
            ttk.Button(form, text="选择", command=action).grid(row=row, column=2, padx=(8, 0), pady=4)
        preview = ttk.LabelFrame(self, text="首帧预览：拖拽新建选区；拖动框内移动；拖动右下角缩放", padding=8)
        preview.grid(row=1, column=0, pady=(10, 0), sticky="nsew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, background="#20242a", highlightthickness=0)
        self.canvas.grid(sticky="nsew")
        for event, handler in (("<ButtonPress-1>", self.on_press), ("<B1-Motion>", self.on_drag), ("<ButtonRelease-1>", self.on_release)):
            self.canvas.bind(event, handler)
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, pady=10, sticky="ew")
        self.start_button = ttk.Button(actions, text="开始批量处理", command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        ttk.Progressbar(actions, variable=self.progress_var, maximum=100).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(self, textvariable=self.status_var).grid(row=3, column=0, sticky="w")
        self.log = tk.Text(self, height=10, state="disabled", wrap="word")
        self.log.grid(row=4, column=0, pady=(8, 0), sticky="nsew")

    def write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_source(self) -> None:
        selected = filedialog.askdirectory(title="选择只包含待处理视频的源文件夹")
        if selected:
            self.source_var.set(selected)
            self.load_preview()

    def choose_destination(self) -> None:
        selected = filedialog.askdirectory(title="选择输出文件夹")
        if selected:
            self.destination_var.set(selected)

    def choose_image(self) -> None:
        selected = filedialog.askopenfilename(title="选择替换图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")])
        if selected:
            self.image_var.set(selected)

    def load_preview(self) -> None:
        source = Path(self.source_var.get())
        if not source.is_dir():
            return
        try:
            tools = ToolResolver.resolve()
            videos = scan_videos(source)
            if not videos:
                self.status_var.set("源文件夹第一层没有支持的视频。")
                return
            frame = temporary_frame_path()
            extract_first_frame(tools, videos[0], frame)
            with Image.open(frame) as image:
                original = image.convert("RGB")
                geometry = PreviewGeometry(original.width, original.height, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
                displayed = original.resize((round(original.width * geometry.scale), round(original.height * geometry.scale)), Image.Resampling.LANCZOS)
            frame.unlink(missing_ok=True)
            self.preview_geometry = geometry
            self.preview_photo = ImageTk.PhotoImage(displayed)
            self.canvas.delete("all")
            self.canvas.create_image(geometry.offset_x, geometry.offset_y, anchor="nw", image=self.preview_photo, tags="preview")
            self.draw_region()
            self.status_var.set(f"预览：{videos[0].name}；找到 {len(videos)} 个视频。工具来源：{tools.source}。")
            self.write_log(self.status_var.get())
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("无法加载预览", str(error))

    def draw_region(self) -> None:
        self.canvas.delete("region")
        left, top, right, bottom = self.rectangle
        self.canvas.create_rectangle(left, top, right, bottom, outline="#ffcc33", width=3, tags="region")
        self.canvas.create_rectangle(right - 6, bottom - 6, right + 6, bottom + 6, fill="#ffcc33", outline="", tags="region")

    def on_press(self, event: tk.Event) -> None:
        left, top, right, bottom = self.rectangle
        self.drag_anchor = (event.x, event.y)
        if abs(event.x - right) <= 14 and abs(event.y - bottom) <= 14:
            self.drag_mode = "resize"
        elif left <= event.x <= right and top <= event.y <= bottom:
            self.drag_mode = "move"
        else:
            self.rectangle = [event.x, event.y, event.x + 1, event.y + 1]
            self.drag_mode = "new"
        self.draw_region()

    def on_drag(self, event: tk.Event) -> None:
        if not self.drag_mode:
            return
        left, top, right, bottom = self.rectangle
        dx, dy = event.x - self.drag_anchor[0], event.y - self.drag_anchor[1]
        if self.drag_mode == "move":
            self.rectangle = [left + dx, top + dy, right + dx, bottom + dy]
            self.drag_anchor = (event.x, event.y)
        elif self.drag_mode in {"resize", "new"}:
            self.rectangle[2], self.rectangle[3] = event.x, event.y
        self.draw_region()

    def on_release(self, event: tk.Event) -> None:
        if self.preview_geometry:
            left, top, right, bottom = self.rectangle
            self.rectangle = [min(left, right), min(top, bottom), max(left, right), max(top, bottom)]
            self.draw_region()
        self.drag_mode = None

    def selected_region(self) -> Region:
        if not self.preview_geometry:
            raise ValueError("请先选择源文件夹以加载首帧预览。")
        return self.preview_geometry.to_region(*self.rectangle)

    def start(self) -> None:
        source = Path(self.source_var.get())
        destination = Path(self.destination_var.get())
        image = Path(self.image_var.get())
        if not source.is_dir() or not image.is_file() or not self.destination_var.get():
            messagebox.showwarning("信息不完整", "请选择有效的源文件夹、目标文件夹和替换图片。")
            return
        if source.resolve() == destination.resolve():
            messagebox.showwarning("目录冲突", "目标文件夹必须与源文件夹不同，以保护源视频。")
            return
        videos = scan_videos(source)
        if not videos:
            messagebox.showwarning("没有视频", "源文件夹第一层没有支持的视频。")
            return
        try:
            tools = ToolResolver.resolve()
            region = self.selected_region()
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("无法开始", str(error))
            return
        self.processor = VideoProcessor(tools, logger=lambda text: self.events.put(("log", text)))
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0)
        self.write_log(f"开始处理 {len(videos)} 个视频；FFmpeg 来源：{tools.source}。")
        thread = threading.Thread(target=self._worker, args=(image, videos, destination, region), daemon=True)
        thread.start()
        self.root.after(80, self.poll_events)

    def _worker(self, image: Path, videos: list[Path], destination: Path, region: Region) -> None:
        assert self.processor
        summary = self.processor.process_batch(
            image, videos, destination, region,
            lambda current, total, video, state: self.events.put(("progress", (current, total, video.name, state))),
        )
        self.events.put(("finished", summary))

    def poll_events(self) -> None:
        pending = False
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.write_log(str(payload))
            elif kind == "progress":
                current, total, name, state = payload  # type: ignore[misc]
                self.progress_var.set(current / total * 100)
                self.status_var.set(f"{state}：{name}（{current}/{total}）")
            elif kind == "finished":
                summary = payload  # type: ignore[assignment]
                self.start_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
                message = f"完成：成功 {len(summary['success'])}，失败 {len(summary['failed'])}，取消 {len(summary['cancelled'])}。"
                self.status_var.set(message)
                self.write_log(message)
                for category in ("success", "failed", "cancelled"):
                    for item in summary[category]:
                        self.write_log(f"[{category}] {item}")
                return
            pending = True
        if self.processor and (pending or self.start_button.instate(["disabled"])):
            self.root.after(80, self.poll_events)

    def cancel(self) -> None:
        if self.processor:
            self.processor.cancel()
            self.status_var.set("正在取消当前处理任务。")
            self.write_log("用户请求取消。")
