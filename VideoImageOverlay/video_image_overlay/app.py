from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .engine import Region, ToolResolver, VideoProcessor, extract_first_frame, scan_videos, temporary_frame_path
from .gui_math import PreviewGeometry
from .presets import install_presets
from .settings import AppSettings, SettingsStore


@dataclass
class PreviewSurface:
    canvas: tk.Canvas
    geometry: PreviewGeometry | None = None
    photo: ImageTk.PhotoImage | None = None
    rectangle: list[float] | None = None
    drag_mode: str | None = None
    drag_anchor: tuple[float, float] = (0.0, 0.0)


class VideoImageOverlayApp(ttk.Frame):
    CANVAS_WIDTH = 760
    CANVAS_HEIGHT = 428

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=16)
        self.root = root
        self.startup_messages: list[str] = []
        self.settings_store = SettingsStore()
        self.saved_settings = self.settings_store.load(self.startup_messages.append)
        self._settings_ready = False
        self._save_after: str | None = None
        self._preview_render_after: str | None = None
        self.root.title("VideoImageOverlay v0.3.0")
        self.root.minsize(960, 780)
        self.root.geometry(f"{self.saved_settings.window_width}x{self.saved_settings.window_height}")
        self._configure_style()
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.source_var = tk.StringVar(value=self.saved_settings.source_path)
        self.destination_var = tk.StringVar(value=self.saved_settings.destination_path)
        self.image_var = tk.StringVar(value=self.saved_settings.image_path)
        self.status_var = tk.StringVar(value="请选择源文件夹、目标文件夹和替换图片。")
        self.progress_var = tk.DoubleVar(value=0)
        self.region = Region(*self.saved_settings.region)
        self.original_frame: Image.Image | None = None
        self.preview_geometry: PreviewGeometry | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.rectangle = [170.0, 100.0, 390.0, 220.0]
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.processor: VideoProcessor | None = None
        self.preview_window: tk.Toplevel | None = None
        self.preview_surface: PreviewSurface | None = None
        self.preview_zoom_var = tk.StringVar(value=self.saved_settings.preview_zoom)
        self.preview_fullscreen = False
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Configure>", self.on_window_configure)
        for variable in (self.source_var, self.destination_var, self.image_var):
            variable.trace_add("write", self.on_path_changed)
        self.root.after_idle(self.restore_startup_state)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", foreground="#475569")
        style.configure("Hint.TLabel", foreground="#64748b")

    def _build(self) -> None:
        form = ttk.LabelFrame(self, text="输入与输出", style="Card.TLabelframe")
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        fields = (
            ("源文件夹", self.source_var, self.choose_source),
            ("目标文件夹", self.destination_var, self.choose_destination),
            ("替换图片", self.image_var, self.choose_image),
        )
        for row, (label, variable, action) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, padx=(0, 10), pady=5, sticky="w")
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, pady=5, sticky="ew")
            ttk.Button(form, text="选择", command=action).grid(row=row, column=2, padx=(10, 0), pady=5)
        ttk.Button(form, text="安装常用素材", command=self.install_common_presets).grid(row=3, column=1, pady=(8, 2), sticky="w")

        preview = ttk.LabelFrame(self, text="首帧预览", style="Card.TLabelframe")
        preview.grid(row=1, column=0, pady=(14, 0), sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, background="#20242a", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.main_surface = PreviewSurface(self.canvas)
        self._bind_surface(self.main_surface)
        ttk.Label(preview, text="拖拽新建选区 · 框内移动 · 右下角缩放 · 选区会自动保存", style="Hint.TLabel").grid(row=1, column=0, pady=(8, 0), sticky="w")

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, pady=12, sticky="ew")
        self.start_button = ttk.Button(actions, text="开始批量处理", style="Primary.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="放大预览", command=self.open_preview).pack(side="left", padx=(8, 0))
        ttk.Progressbar(actions, variable=self.progress_var, maximum=100).pack(side="left", fill="x", expand=True, padx=(16, 0))
        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel").grid(row=3, column=0, pady=(0, 4), sticky="w")
        self.log = tk.Text(self, height=9, state="disabled", wrap="word", background="#f8fafc", foreground="#334155", relief="flat", padx=8, pady=8)
        self.log.grid(row=4, column=0, sticky="nsew")

    def _bind_surface(self, surface: PreviewSurface) -> None:
        surface.canvas.bind("<ButtonPress-1>", lambda event: self._on_press(surface, event))
        surface.canvas.bind("<B1-Motion>", lambda event: self._on_drag(surface, event))
        surface.canvas.bind("<ButtonRelease-1>", lambda event: self._on_release(surface, event))

    def write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def restore_startup_state(self) -> None:
        if self.saved_settings.window_state == "zoomed":
            self.root.state("zoomed")
        for message in self.startup_messages:
            self.write_log(message)
        self._settings_ready = True
        source = Path(self.source_var.get()) if self.source_var.get() else None
        if source and source.is_dir():
            self.load_preview()
        elif source:
            message = f"已恢复源路径，但路径不可用：{source}"
            self.status_var.set(message)
            self.write_log(message)
        self.persist_settings()

    def _preview_size(self) -> tuple[int, int]:
        width = max(800, self.saved_settings.preview_width)
        height = max(600, self.saved_settings.preview_height)
        if self.preview_window and self.preview_window.winfo_exists():
            width = max(800, self.preview_window.winfo_width())
            height = max(600, self.preview_window.winfo_height())
        return width, height

    def collect_settings(self) -> AppSettings:
        state = self.root.state()
        if state not in {"normal", "zoomed"}:
            state = "normal"
        preview_width, preview_height = self._preview_size()
        return AppSettings(
            source_path=self.source_var.get(),
            destination_path=self.destination_var.get(),
            image_path=self.image_var.get(),
            region=(self.region.x, self.region.y, self.region.width, self.region.height),
            position_mode="normalized",
            window_width=max(640, self.root.winfo_width()),
            window_height=max(480, self.root.winfo_height()),
            window_state=state,
            preview_width=preview_width,
            preview_height=preview_height,
            preview_zoom=self.preview_zoom_var.get(),
        )

    def persist_settings(self) -> None:
        if not self._settings_ready:
            return
        try:
            self.settings_store.save(self.collect_settings())
        except OSError as error:
            self.write_log(f"无法保存 settings.json：{error}")

    def schedule_persist(self) -> None:
        if not self._settings_ready:
            return
        if self._save_after:
            self.root.after_cancel(self._save_after)
        self._save_after = self.root.after(300, self.persist_settings)

    def on_path_changed(self, *_: object) -> None:
        self.schedule_persist()

    def on_window_configure(self, event: tk.Event) -> None:
        if event.widget == self.root and self.root.state() != "iconic":
            self.schedule_persist()

    def on_close(self) -> None:
        self.close_preview()
        self.persist_settings()
        self.root.destroy()

    def choose_source(self) -> None:
        selected = filedialog.askdirectory(title="选择只包含待处理视频的源文件夹")
        if selected:
            self.source_var.set(selected)
            self.persist_settings()
            self.load_preview()

    def choose_destination(self) -> None:
        selected = filedialog.askdirectory(title="选择输出文件夹")
        if selected:
            self.destination_var.set(selected)
            self.persist_settings()

    def choose_image(self) -> None:
        selected = filedialog.askopenfilename(title="选择替换图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")])
        if selected:
            self.image_var.set(selected)
            self.persist_settings()

    def install_common_presets(self) -> None:
        result = install_presets(self.settings_store.base_directory, self.write_log)
        self.status_var.set(f"常用素材：新增 {len(result.installed)}，跳过 {len(result.skipped)}，失败 {len(result.failed)}。")

    def load_preview(self) -> None:
        source = Path(self.source_var.get())
        if not source.is_dir():
            return
        frame: Path | None = None
        try:
            tools = ToolResolver.resolve()
            videos = scan_videos(source)
            if not videos:
                message = "源文件夹第一层没有支持的视频。"
                self.status_var.set(message)
                self.write_log(message)
                return
            frame = temporary_frame_path()
            extract_first_frame(tools, videos[0], frame)
            with Image.open(frame) as image:
                self.original_frame = image.convert("RGB")
            self._render_main()
            message = f"预览：{videos[0].name}；找到 {len(videos)} 个视频。工具来源：{tools.source}。"
            self.status_var.set(message)
            self.write_log(message)
        except Exception as error:  # noqa: BLE001
            message = f"无法加载预览：{error}"
            self.status_var.set(message)
            self.write_log(message)
        finally:
            if frame:
                frame.unlink(missing_ok=True)

    def _render_main(self) -> None:
        if not self.original_frame:
            return
        surface = self.main_surface
        surface.geometry = PreviewGeometry(self.original_frame.width, self.original_frame.height, self.CANVAS_WIDTH, self.CANVAS_HEIGHT)
        displayed = self.original_frame.resize((round(self.original_frame.width * surface.geometry.scale), round(self.original_frame.height * surface.geometry.scale)), Image.Resampling.LANCZOS)
        surface.photo = ImageTk.PhotoImage(displayed)
        surface.canvas.delete("all")
        surface.canvas.create_image(surface.geometry.offset_x, surface.geometry.offset_y, anchor="nw", image=surface.photo, tags="preview")
        surface.rectangle = list(surface.geometry.from_region(self.region))
        self.preview_geometry = surface.geometry
        self.preview_photo = surface.photo
        self.rectangle = surface.rectangle
        self._draw_surface(surface)

    def _large_display_size(self) -> tuple[int, int]:
        assert self.original_frame and self.preview_surface and self.preview_window
        zoom = self.preview_zoom_var.get()
        if zoom == "fit":
            self.preview_window.update_idletasks()
            viewport_width = max(400, self.preview_surface.canvas.winfo_width())
            viewport_height = max(300, self.preview_surface.canvas.winfo_height())
            scale = min(viewport_width / self.original_frame.width, viewport_height / self.original_frame.height)
        else:
            scale = float(zoom.rstrip("%")) / 100
        return max(1, round(self.original_frame.width * scale)), max(1, round(self.original_frame.height * scale))

    def _render_large(self) -> None:
        if not self.preview_surface or not self.preview_window or not self.preview_window.winfo_exists() or not self.original_frame:
            return
        surface = self.preview_surface
        width, height = self._large_display_size()
        surface.geometry = PreviewGeometry(self.original_frame.width, self.original_frame.height, width, height)
        displayed = self.original_frame.resize((width, height), Image.Resampling.LANCZOS)
        surface.photo = ImageTk.PhotoImage(displayed)
        surface.canvas.delete("all")
        surface.canvas.configure(scrollregion=(0, 0, width, height))
        surface.canvas.create_image(0, 0, anchor="nw", image=surface.photo, tags="preview")
        surface.rectangle = list(surface.geometry.from_region(self.region))
        self._draw_surface(surface)

    def _draw_surface(self, surface: PreviewSurface) -> None:
        surface.canvas.delete("region")
        if not surface.rectangle:
            return
        left, top, right, bottom = surface.rectangle
        surface.canvas.create_rectangle(left, top, right, bottom, outline="#fbbf24", width=3, tags="region")
        surface.canvas.create_rectangle(right - 7, bottom - 7, right + 7, bottom + 7, fill="#fbbf24", outline="", tags="region")

    def draw_region(self) -> None:
        self.main_surface.rectangle = self.rectangle
        self._draw_surface(self.main_surface)

    def _event_xy(self, surface: PreviewSurface, event: tk.Event) -> tuple[float, float]:
        return surface.canvas.canvasx(event.x), surface.canvas.canvasy(event.y)

    def _on_press(self, surface: PreviewSurface, event: tk.Event) -> None:
        if not surface.geometry or not surface.rectangle:
            return
        x, y = self._event_xy(surface, event)
        left, top, right, bottom = surface.rectangle
        surface.drag_anchor = (x, y)
        if abs(x - right) <= 18 and abs(y - bottom) <= 18:
            surface.drag_mode = "resize"
        elif left <= x <= right and top <= y <= bottom:
            surface.drag_mode = "move"
        else:
            surface.rectangle = [x, y, x + 1, y + 1]
            surface.drag_mode = "new"
        self._draw_surface(surface)

    def _on_drag(self, surface: PreviewSurface, event: tk.Event) -> None:
        if not surface.drag_mode or not surface.rectangle:
            return
        x, y = self._event_xy(surface, event)
        left, top, right, bottom = surface.rectangle
        dx, dy = x - surface.drag_anchor[0], y - surface.drag_anchor[1]
        if surface.drag_mode == "move":
            surface.rectangle = [left + dx, top + dy, right + dx, bottom + dy]
            surface.drag_anchor = (x, y)
        else:
            surface.rectangle[2], surface.rectangle[3] = x, y
        self._draw_surface(surface)

    def _on_release(self, surface: PreviewSurface, event: tk.Event) -> None:
        if not surface.geometry or not surface.rectangle:
            surface.drag_mode = None
            return
        left, top, right, bottom = surface.rectangle
        self.region = surface.geometry.to_region(min(left, right), min(top, bottom), max(left, right), max(top, bottom))
        surface.drag_mode = None
        self._render_main()
        self._render_large()
        self.persist_settings()

    def on_press(self, event: tk.Event) -> None:
        self._on_press(self.main_surface, event)

    def on_drag(self, event: tk.Event) -> None:
        self._on_drag(self.main_surface, event)

    def on_release(self, event: tk.Event) -> None:
        self._on_release(self.main_surface, event)

    def open_preview(self) -> None:
        if not self.original_frame:
            self.status_var.set("请先选择有效源文件夹并加载首帧预览。")
            self.write_log(self.status_var.get())
            return
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.deiconify()
            self.preview_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.preview_window = window
        window.title("VideoImageOverlay · 放大预览")
        window.geometry(f"{self.saved_settings.preview_width}x{self.saved_settings.preview_height}")
        window.minsize(800, 600)
        window.protocol("WM_DELETE_WINDOW", self.close_preview)
        window.bind("<F11>", self.toggle_fullscreen)
        window.bind("<Escape>", self.exit_fullscreen)
        window.bind("<Configure>", self.on_preview_configure)
        toolbar = ttk.Frame(window, padding=(12, 10))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="缩放：").pack(side="left")
        zoom = ttk.Combobox(toolbar, textvariable=self.preview_zoom_var, values=("fit", "100%", "150%", "200%"), state="readonly", width=8)
        zoom.pack(side="left")
        zoom.bind("<<ComboboxSelected>>", lambda _event: (self._render_large(), self.schedule_persist()))
        ttk.Button(toolbar, text="全屏 F11", command=self.toggle_fullscreen).pack(side="left", padx=(10, 0))
        ttk.Label(toolbar, text="Esc 退出全屏 · 关闭按钮关闭预览", style="Hint.TLabel").pack(side="left", padx=(14, 0))
        content = ttk.Frame(window)
        content.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        canvas = tk.Canvas(content, background="#20242a", highlightthickness=0, xscrollincrement=1, yscrollincrement=1)
        xbar = ttk.Scrollbar(content, orient="horizontal", command=canvas.xview)
        ybar = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self.preview_surface = PreviewSurface(canvas)
        self._bind_surface(self.preview_surface)
        window.update_idletasks()
        self._render_large()

    def on_preview_configure(self, event: tk.Event) -> None:
        if self.preview_window and event.widget == self.preview_window:
            if self.preview_zoom_var.get() == "fit":
                if self._preview_render_after:
                    self.preview_window.after_cancel(self._preview_render_after)
                self._preview_render_after = self.preview_window.after_idle(self._render_large)
            self.schedule_persist()

    def toggle_fullscreen(self, event: tk.Event | None = None) -> str:
        if not self.preview_window or not self.preview_window.winfo_exists():
            return "break"
        self.preview_fullscreen = not bool(self.preview_window.attributes("-fullscreen"))
        self.preview_window.attributes("-fullscreen", self.preview_fullscreen)
        return "break"

    def exit_fullscreen(self, event: tk.Event | None = None) -> str:
        if self.preview_window and self.preview_window.winfo_exists() and self.preview_fullscreen:
            self.preview_fullscreen = False
            self.preview_window.attributes("-fullscreen", False)
        return "break"

    def close_preview(self) -> None:
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_fullscreen = False
            self.preview_window.destroy()
        self.preview_window = None
        self.preview_surface = None
        self.schedule_persist()

    def selected_region(self) -> Region:
        if not self.preview_geometry:
            raise ValueError("请先选择源文件夹以加载首帧预览。")
        return self.region

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
            self.status_var.set(f"无法开始：{error}")
            self.write_log(self.status_var.get())
            return
        self.processor = VideoProcessor(tools, logger=lambda text: self.events.put(("log", text)))
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_var.set(0)
        self.persist_settings()
        self.write_log(f"开始处理 {len(videos)} 个视频；FFmpeg 来源：{tools.source}。")
        threading.Thread(target=self._worker, args=(image, videos, destination, region), daemon=True).start()
        self.root.after(80, self.poll_events)

    def _worker(self, image: Path, videos: list[Path], destination: Path, region: Region) -> None:
        assert self.processor
        summary = self.processor.process_batch(image, videos, destination, region, lambda current, total, video, state: self.events.put(("progress", (current, total, video.name, state))))
        self.events.put(("finished", summary))

    def poll_events(self) -> None:
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
        if self.processor and self.start_button.instate(["disabled"]):
            self.root.after(80, self.poll_events)

    def cancel(self) -> None:
        if self.processor:
            self.processor.cancel()
            self.status_var.set("正在取消当前处理任务。")
            self.write_log("用户请求取消。")
