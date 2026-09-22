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
from .presets import app_icon_path, install_presets, preset_is_present, remove_presets
from .settings import AppSettings, SettingsStore


@dataclass
class PreviewSurface:
    canvas: tk.Canvas
    geometry: PreviewGeometry | None = None
    photo: ImageTk.PhotoImage | None = None
    rectangle: list[float] | None = None
    drag_mode: str | None = None
    drag_anchor: tuple[float, float] = (0.0, 0.0)
    pan_x: float = 0.0
    pan_y: float = 0.0
    pan_anchor: tuple[float, float] = (0.0, 0.0)
    zoom: float = 1.0
    magnifier_photo: ImageTk.PhotoImage | None = None
    content_origin_x: float = 0.0
    content_origin_y: float = 0.0
    image_item: int | None = None
    region_item: int | None = None
    handle_item: int | None = None
    magnifier_item: int | None = None
    magnifier_border_item: int | None = None
    magnifier_source_box: tuple[float, float, float, float] | None = None


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
        self._zoom_render_pending = False
        self._zoom_after: str | None = None
        self._zoom_request: tuple[PreviewSurface, float, float, float, float] | None = None
        self._large_quality_after: str | None = None
        self._main_render_pending = False
        self._rendering_preview = False
        self._last_canvas_size: tuple[int, int] | None = None
        self.root.title("VideoImageOverlay v0.4.3")
        try:
            self.root.iconbitmap(str(app_icon_path()))
        except tk.TclError:
            pass
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
        self.preview_zoom_var = tk.StringVar(value="fit" if self.saved_settings.preview_zoom is None else f"{self.saved_settings.preview_zoom:.2f}")
        self.preview_scale_var: tk.DoubleVar | None = None
        self.preview_zoom_label_var = tk.StringVar(value="适应窗口")
        self._updating_preview_scale = False
        self.preset_button: ttk.Button | None = None
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
        self._settings_ready = False
        self.close_preview()
        if self._save_after:
            try: self.root.after_cancel(self._save_after)
            except tk.TclError: pass
            self._save_after = None
        if self._zoom_after:
            try: self.root.after_cancel(self._zoom_after)
            except tk.TclError: pass
            self._zoom_after = None
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
        self._set_preview_zoom(None, persist=False)
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
            self.root.after_idle(self._render_main)
            message = f"预览：{videos[0].name}；找到 {len(videos)} 个视频。工具来源：{tools.source}。"
            self.status_var.set(message)
            self.write_log(message)
        except Exception as error:  # noqa: BLE001
            self.original_frame = None
            self.canvas.delete("all") if hasattr(self, "canvas") else None
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
        if self._large_quality_after:
            try:
                self.root.after_cancel(self._large_quality_after)
            except tk.TclError:
                pass
            self._large_quality_after = None
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_fullscreen = False
            self.preview_window.destroy()
        self.preview_window = None
        self.preview_surface = None
        self.schedule_persist()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try: style.theme_use("vista")
        except tk.TclError: pass
        style.configure("Card.TLabelframe", padding=14)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"), foreground="#0f172a")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#0f172a")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#64748b")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#64748b")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1); self.rowconfigure(2, weight=1)
        head=ttk.Frame(self); head.grid(row=0,column=0,sticky="ew",pady=(0,12)); head.columnconfigure(0,weight=1)
        ttk.Label(head,text="VideoImageOverlay",style="Title.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(head,text="固定区域图片覆盖 · v0.4.3",style="Subtitle.TLabel").grid(row=1,column=0,sticky="w")
        form=ttk.LabelFrame(self,text="输入与输出",style="Card.TLabelframe"); form.grid(row=1,column=0,sticky="ew"); form.columnconfigure(1,weight=1)
        for row,(label,var,action) in enumerate((("源文件夹",self.source_var,self.choose_source),("目标文件夹",self.destination_var,self.choose_destination),("替换图片",self.image_var,self.choose_image))):
            ttk.Label(form,text=label).grid(row=row,column=0,padx=(0,12),pady=6,sticky="w"); ttk.Entry(form,textvariable=var).grid(row=row,column=1,pady=6,sticky="ew"); ttk.Button(form,text="选择",command=action).grid(row=row,column=2,padx=(10,0),pady=6)
        self.preset_button=ttk.Button(form,text=self._preset_button_text(),command=self.install_common_presets); self.preset_button.grid(row=3,column=1,pady=(8,0),sticky="w")
        preview=ttk.LabelFrame(self,text="首帧预览",style="Card.TLabelframe"); preview.grid(row=2,column=0,pady=(12,0),sticky="nsew"); preview.columnconfigure(0,weight=1); preview.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(preview,width=self.CANVAS_WIDTH,height=self.CANVAS_HEIGHT,background="#111827",highlightthickness=0,cursor="crosshair"); self.canvas.grid(row=0,column=0,sticky="nsew")
        self.main_surface=PreviewSurface(self.canvas); self._bind_surface(self.main_surface)
        ttk.Label(preview,text="左键框选/移动/缩放 · 右键平移 · 滚轮连续缩放 · 拖动时显示 2.5× 放大镜",style="Hint.TLabel").grid(row=1,column=0,pady=(8,0),sticky="w")
        actions=ttk.Frame(self); actions.grid(row=3,column=0,pady=12,sticky="ew")
        self.start_button=ttk.Button(actions,text="开始批量处理",style="Primary.TButton",command=self.start); self.start_button.pack(side="left")
        self.cancel_button=ttk.Button(actions,text="取消",command=self.cancel,state="disabled"); self.cancel_button.pack(side="left",padx=(8,0))
        ttk.Button(actions,text="放大预览",command=self.open_preview).pack(side="left",padx=(8,0)); ttk.Progressbar(actions,variable=self.progress_var,maximum=100).pack(side="left",fill="x",expand=True,padx=(16,0))
        ttk.Label(self,textvariable=self.status_var,style="Status.TLabel").grid(row=4,column=0,pady=(0,4),sticky="w")
        self.log=tk.Text(self,height=8,state="disabled",wrap="word",background="#f8fafc",foreground="#334155",relief="flat",padx=10,pady=8); self.log.grid(row=5,column=0,sticky="nsew"); self.rowconfigure(5,weight=1)

    def _bind_surface(self,surface: PreviewSurface) -> None:
        c=surface.canvas; c.bind("<ButtonPress-1>",lambda e:self._on_press(surface,e)); c.bind("<B1-Motion>",lambda e:self._on_drag(surface,e)); c.bind("<ButtonRelease-1>",lambda e:self._on_release(surface,e)); c.bind("<ButtonPress-3>",lambda e:self._on_pan_press(surface,e)); c.bind("<B3-Motion>",lambda e:self._on_pan_drag(surface,e)); c.bind("<ButtonRelease-3>",lambda e:self._on_pan_release(surface,e)); c.bind("<MouseWheel>",lambda e:self._on_wheel(surface,e)); c.bind("<Button-4>",lambda e:self._on_wheel(surface,e,1)); c.bind("<Button-5>",lambda e:self._on_wheel(surface,e,-1)); c.bind("<Configure>",lambda e:self._on_canvas_configure(surface,e))

    def _zoom_value(self) -> float | None:
        value = self.preview_zoom_var.get().strip().lower()
        if value in ("", "fit"):
            return None
        try:
            numeric = float(value.rstrip("%")) / (100 if value.endswith("%") else 1)
        except ValueError:
            return None
        return max(0.5, min(4.0, numeric))

    def _set_preview_zoom(self, value: float | None, *, persist: bool = True) -> None:
        if value is None:
            self.preview_zoom_var.set("fit")
            if self.preview_scale_var is not None:
                self._updating_preview_scale = True
                try:
                    self.preview_scale_var.set(1.0)
                finally:
                    self._updating_preview_scale = False
            self.preview_zoom_label_var.set("适应窗口")
        else:
            numeric = max(0.5, min(4.0, float(value)))
            self.preview_zoom_var.set(f"{numeric:.4f}")
            if self.preview_scale_var is not None:
                self._updating_preview_scale = True
                try:
                    self.preview_scale_var.set(numeric)
                finally:
                    self._updating_preview_scale = False
            self.preview_zoom_label_var.set(f"缩放 {round(numeric * 100):.0f}%")
        if persist:
            self.schedule_persist()

    def collect_settings(self) -> AppSettings:
        state=self.root.state() if self.root.state() in {"normal","zoomed"} else "normal"
        return AppSettings(self.source_var.get(),self.destination_var.get(),self.image_var.get(),(self.region.x,self.region.y,self.region.width,self.region.height),"normalized",max(640,self.root.winfo_width()),max(480,self.root.winfo_height()),state,*self._preview_size(),self._zoom_value())

    def _render_main(self) -> None:
        if not self.original_frame: return
        s=self.main_surface; w=self.canvas.winfo_width() or self.CANVAS_WIDTH; h=self.canvas.winfo_height() or self.CANVAS_HEIGHT; s.geometry=PreviewGeometry(self.original_frame.width,self.original_frame.height,w,h,s.zoom); size=(max(1,round(self.original_frame.width*s.geometry.scale)),max(1,round(self.original_frame.height*s.geometry.scale))); s.photo=ImageTk.PhotoImage(self.original_frame.resize(size,Image.Resampling.LANCZOS)); s.canvas.delete("all"); s.canvas.create_image(s.geometry.offset_x+s.pan_x,s.geometry.offset_y+s.pan_y,anchor="nw",image=s.photo,tags="preview"); s.rectangle=[v+(s.pan_x if i%2==0 else s.pan_y) for i,v in enumerate(s.geometry.from_region(self.region))]; self.preview_geometry=s.geometry; self.rectangle=s.rectangle; self._draw_surface(s)

    def _large_display_size(self):
        assert self.original_frame and self.preview_surface and self.preview_window
        z=self._zoom_value()
        if z is None:
            self.preview_window.update_idletasks(); z=min(max(400,self.preview_surface.canvas.winfo_width())/self.original_frame.width,max(300,self.preview_surface.canvas.winfo_height())/self.original_frame.height)
        return max(1,round(self.original_frame.width*z)),max(1,round(self.original_frame.height*z))

    def _canvas_item_exists(self, canvas: tk.Canvas, item: int | None) -> bool:
        if item is None:
            return False
        try:
            return bool(canvas.type(item))
        except tk.TclError:
            return False

    def _large_layout(self, width: int, height: int) -> tuple[int, int, float, float]:
        assert self.preview_surface
        canvas = self.preview_surface.canvas
        viewport_width = max(1, canvas.winfo_width())
        viewport_height = max(1, canvas.winfo_height())
        scroll_width = max(width, viewport_width)
        scroll_height = max(height, viewport_height)
        origin_x = (viewport_width - width) / 2 if width <= viewport_width else 0.0
        origin_y = (viewport_height - height) / 2 if height <= viewport_height else 0.0
        return scroll_width, scroll_height, origin_x, origin_y

    def _render_large(self, restore_view: bool = True, quality: str = "final") -> None:
        if not self.preview_surface or not self.preview_window or not self.preview_window.winfo_exists() or not self.original_frame:
            return
        surface = self.preview_surface
        canvas = surface.canvas
        old_x = canvas.xview()[0] if restore_view else 0.0
        old_y = canvas.yview()[0] if restore_view else 0.0
        width, height = self._large_display_size()
        scroll_width, scroll_height, origin_x, origin_y = self._large_layout(width, height)
        surface.geometry = PreviewGeometry(self.original_frame.width, self.original_frame.height, width, height)
        resampling = Image.Resampling.BILINEAR if quality == "interactive" else Image.Resampling.LANCZOS
        surface.photo = ImageTk.PhotoImage(self.original_frame.resize((width, height), resampling))
        canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
        if self._canvas_item_exists(canvas, surface.image_item):
            canvas.itemconfigure(surface.image_item, image=surface.photo)
            canvas.coords(surface.image_item, origin_x, origin_y)
        else:
            surface.image_item = canvas.create_image(origin_x, origin_y, anchor="nw", image=surface.photo, tags=("preview", "preview-image"))
        surface.content_origin_x = origin_x
        surface.content_origin_y = origin_y
        base_rectangle = surface.geometry.from_region(self.region)
        surface.rectangle = [base_rectangle[0] + origin_x, base_rectangle[1] + origin_y, base_rectangle[2] + origin_x, base_rectangle[3] + origin_y]
        self._draw_surface(surface)
        if restore_view:
            canvas.update_idletasks()
            if width <= canvas.winfo_width():
                canvas.xview_moveto(0.0)
            else:
                canvas.xview_moveto(max(0.0, min(1.0, old_x)))
            if height <= canvas.winfo_height():
                canvas.yview_moveto(0.0)
            else:
                canvas.yview_moveto(max(0.0, min(1.0, old_y)))

    def _schedule_large_quality_render(self) -> None:
        if self._large_quality_after:
            try:
                self.root.after_cancel(self._large_quality_after)
            except tk.TclError:
                pass
        self._large_quality_after = self.root.after(80, self._flush_large_quality_render)

    def _flush_large_quality_render(self) -> None:
        self._large_quality_after = None
        self._render_large(restore_view=True, quality="final")

    def _draw_surface(self, surface: PreviewSurface) -> None:
        canvas = surface.canvas
        if not surface.rectangle:
            return
        left, top, right, bottom = surface.rectangle
        if self._canvas_item_exists(canvas, surface.region_item):
            canvas.coords(surface.region_item, left, top, right, bottom)
        else:
            surface.region_item = canvas.create_rectangle(left, top, right, bottom, outline="#facc15", width=3, tags=("region", "selection"))
        if self._canvas_item_exists(canvas, surface.handle_item):
            canvas.coords(surface.handle_item, right - 7, bottom - 7, right + 7, bottom + 7)
        else:
            surface.handle_item = canvas.create_rectangle(right - 7, bottom - 7, right + 7, bottom + 7, fill="#facc15", outline="", tags=("region", "handle"))
        if self._canvas_item_exists(canvas, surface.image_item):
            canvas.tag_raise(surface.region_item, surface.image_item)
            canvas.tag_raise(surface.handle_item, surface.region_item)
        if self._canvas_item_exists(canvas, surface.magnifier_item):
            canvas.tag_raise(surface.magnifier_item)
        if self._canvas_item_exists(canvas, surface.magnifier_border_item):
            canvas.tag_raise(surface.magnifier_border_item)

    def _event_xy(self,surface,event): return surface.canvas.canvasx(event.x),surface.canvas.canvasy(event.y)

    def _on_press(self,surface,event):
        if not surface.geometry or not surface.rectangle:return "break"
        x,y=self._event_xy(surface,event); l,t,r,b=surface.rectangle; surface.drag_anchor=(x,y); surface.drag_mode="resize" if abs(x-r)<=18 and abs(y-b)<=18 else ("move" if l<=x<=r and t<=y<=b else "new")
        if surface.drag_mode=="new":surface.rectangle=[x,y,x+1,y+1]
        self._draw_surface(surface); return "break"

    def _on_drag(self, surface, event):
        if not surface.drag_mode or surface.drag_mode == "pan" or not surface.rectangle:
            return "break"
        x, y = self._event_xy(surface, event)
        left, top, right, bottom = surface.rectangle
        dx, dy = x - surface.drag_anchor[0], y - surface.drag_anchor[1]
        if surface.drag_mode == "move":
            surface.rectangle = [left + dx, top + dy, right + dx, bottom + dy]
            surface.drag_anchor = (x, y)
        else:
            surface.rectangle[2], surface.rectangle[3] = x, y
        self._draw_surface(surface)
        self._draw_magnifier(surface, x, y, event.x, event.y)
        return "break"

    def _on_release(self, surface, event):
        if not surface.geometry or not surface.rectangle:
            surface.drag_mode = None
            return "break"
        left, top, right, bottom = surface.rectangle
        origin_x = surface.content_origin_x if surface is self.preview_surface else 0.0
        origin_y = surface.content_origin_y if surface is self.preview_surface else 0.0
        pan_x = surface.pan_x if surface is not self.preview_surface else 0.0
        pan_y = surface.pan_y if surface is not self.preview_surface else 0.0
        self.region = surface.geometry.to_region(
            min(left, right) - origin_x - pan_x,
            min(top, bottom) - origin_y - pan_y,
            max(left, right) - origin_x - pan_x,
            max(top, bottom) - origin_y - pan_y,
        )
        surface.drag_mode = None
        surface.canvas.delete("magnifier")
        surface.magnifier_item = None
        surface.magnifier_border_item = None
        self._render_main()
        self._render_large()
        self.persist_settings()
        return "break"

    def _on_pan_press(self,surface,event): surface.drag_mode="pan"; surface.pan_anchor=(event.x,event.y); surface.canvas.scan_mark(event.x,event.y); return "break"
    def _on_pan_drag(self,surface,event):
        if surface.drag_mode!="pan":return "break"
        if surface is self.preview_surface:surface.canvas.scan_dragto(event.x,event.y,gain=1)
        else:surface.pan_x+=event.x-surface.pan_anchor[0]; surface.pan_y+=event.y-surface.pan_anchor[1]; surface.pan_anchor=(event.x,event.y); self._render_main()
        return "break"
    def _on_pan_release(self,surface,event):surface.drag_mode=None; return "break"

    def _on_wheel(self,surface,event,direction=0):
        step=direction or (1 if event.delta>0 else -1)
        if surface is self.preview_surface:self.preview_zoom_var.set(f"{max(.5,min(4.0,(self._zoom_value() or 1.0)+step*.1)):.2f}"); self._render_large()
        else:surface.zoom=max(.5,min(4.0,surface.zoom+step*.1)); self._render_main()
        self.schedule_persist(); return "break"

    def _draw_magnifier(self, surface, x, y, view_x=None, view_y=None):
        if not self.original_frame or not surface.geometry:
            return
        scale = max(surface.geometry.scale, 0.001)
        origin_x = surface.content_origin_x if surface is self.preview_surface else 0.0
        origin_y = surface.content_origin_y if surface is self.preview_surface else 0.0
        source_x = (x - origin_x - surface.geometry.offset_x - surface.pan_x) / scale
        source_y = (y - origin_y - surface.geometry.offset_y - surface.pan_y) / scale
        magnifier_zoom = 4.0
        crop_width = min(self.original_frame.width, 220 / (magnifier_zoom * scale))
        crop_height = min(self.original_frame.height, 180 / (magnifier_zoom * scale))
        left = max(0.0, min(self.original_frame.width - crop_width, source_x - crop_width / 2))
        top = max(0.0, min(self.original_frame.height - crop_height, source_y - crop_height / 2))
        surface.magnifier_source_box = (left, top, left + crop_width, top + crop_height)
        crop = self.original_frame.crop((round(left), round(top), round(left + crop_width), round(top + crop_height))).resize((220, 180), Image.Resampling.LANCZOS)
        surface.magnifier_photo = ImageTk.PhotoImage(crop)
        canvas = surface.canvas
        pointer_x = float(view_x if view_x is not None else x)
        pointer_y = float(view_y if view_y is not None else y)
        viewport_width = max(220, canvas.winfo_width())
        viewport_height = max(180, canvas.winfo_height())
        px = pointer_x + 18
        py = pointer_y + 18
        if px + 220 > viewport_width:
            px = pointer_x - 238
        if py + 180 > viewport_height:
            py = pointer_y - 198
        px = max(8.0, min(px, viewport_width - 228.0))
        py = max(8.0, min(py, viewport_height - 188.0))
        if surface.magnifier_item:
            canvas.delete(surface.magnifier_item)
        if surface.magnifier_border_item:
            canvas.delete(surface.magnifier_border_item)
        surface.magnifier_item = canvas.create_image(px, py, anchor="nw", image=surface.magnifier_photo, tags=("magnifier", "magnifier-image"))
        surface.magnifier_border_item = canvas.create_rectangle(px, py, px + 220, py + 180, outline="#facc15", width=2, tags=("magnifier", "magnifier-border"))
        canvas.tag_raise(surface.magnifier_item)
        canvas.tag_raise(surface.magnifier_border_item)

    def _on_preview_scale(self, value: str) -> None:
        if self._updating_preview_scale:
            return
        self._set_preview_zoom(float(value))
        self._render_large(restore_view=True, quality="interactive")
        self._schedule_large_quality_render()

    def open_preview(self):
        if not self.original_frame:self.status_var.set("请先选择有效源文件夹并加载首帧预览。"); self.write_log(self.status_var.get()); return
        if self.preview_window and self.preview_window.winfo_exists():self.preview_window.deiconify(); self.preview_window.lift(); return
        w=tk.Toplevel(self.root); self.preview_window=w; w.title("VideoImageOverlay · 放大预览"); w.geometry(f"{self.saved_settings.preview_width}x{self.saved_settings.preview_height}"); w.minsize(800,600);
        try: w.iconbitmap(str(app_icon_path()))
        except tk.TclError: pass
        w.protocol("WM_DELETE_WINDOW",self.close_preview); w.bind("<F11>",self.toggle_fullscreen); w.bind("<Escape>",self.exit_fullscreen); w.bind("<Configure>",self.on_preview_configure)
        bar=ttk.Frame(w,padding=(14,12)); bar.pack(fill="x"); ttk.Label(bar,text="缩放").pack(side="left"); self.preview_scale_var=tk.DoubleVar(value=self._zoom_value() or 1.0); self._set_preview_zoom(self._zoom_value(), persist=False); scale_widget=ttk.Scale(bar,from_=.5,to=4.0,variable=self.preview_scale_var,orient="horizontal",length=220,command=self._on_preview_scale); scale_widget.pack(side="left",padx=10); scale_widget.bind("<ButtonRelease-1>",lambda _event:self._schedule_large_quality_render()); ttk.Label(bar,textvariable=self.preview_zoom_label_var,style="Hint.TLabel").pack(side="left",padx=(0,12)); ttk.Label(bar,text="滚轮 50%～400% · 右键平移 · Esc 退出全屏",style="Hint.TLabel").pack(side="left")
        content=ttk.Frame(w); content.pack(fill="both",expand=True,padx=12,pady=(0,12)); content.rowconfigure(0,weight=1); content.columnconfigure(0,weight=1); c=tk.Canvas(content,background="#111827",highlightthickness=0); xb=ttk.Scrollbar(content,orient="horizontal",command=c.xview); yb=ttk.Scrollbar(content,orient="vertical",command=c.yview); c.configure(xscrollcommand=xb.set,yscrollcommand=yb.set); c.grid(row=0,column=0,sticky="nsew"); yb.grid(row=0,column=1,sticky="ns"); xb.grid(row=1,column=0,sticky="ew"); self.preview_surface=PreviewSurface(c); self._bind_surface(self.preview_surface); w.update_idletasks(); self._render_large()

    def on_preview_configure(self,event):
        if self.preview_window and event.widget==self.preview_window and self._zoom_value() is None:self.preview_window.after_idle(self._render_large)
        self.schedule_persist()

    def _preset_button_text(self) -> str:
        return "卸载常用素材" if preset_is_present(self.settings_store.base_directory) else "安装常用素材"

    def _refresh_preset_button(self) -> None:
        if self.preset_button and self.preset_button.winfo_exists():
            self.preset_button.configure(text=self._preset_button_text())

    def install_common_presets(self) -> None:
        if preset_is_present(self.settings_store.base_directory):
            result = remove_presets(self.settings_store.base_directory, self.write_log)
            self.status_var.set(f"常用素材卸载：删除 {len(result.removed)}，保留 {len(result.skipped)}，缺失 {len(result.missing)}，失败 {len(result.failed)}。")
        else:
            result = install_presets(self.settings_store.base_directory, self.write_log)
            self.status_var.set(f"常用素材安装：新增 {len(result.installed)}，跳过 {len(result.skipped)}，失败 {len(result.failed)}。")
        self._refresh_preset_button()

    def _on_canvas_configure(self, surface: PreviewSurface, event: tk.Event) -> str:
        if self._rendering_preview or surface is not self.main_surface:
            return "break"
        width, height = int(event.width), int(event.height)
        if width < 100 or height < 100 or not self.original_frame:
            return "break"
        size = (width, height)
        if size == self._last_canvas_size or self._main_render_pending:
            return "break"
        self._last_canvas_size = size
        self._main_render_pending = True
        self.root.after_idle(self._flush_main_render)
        return "break"

    def _flush_main_render(self) -> None:
        self._main_render_pending = False
        if self.original_frame and not self._rendering_preview:
            self._render_main()

    def _render_main(self) -> None:
        if not self.original_frame or self._rendering_preview:
            return
        self._rendering_preview = True
        try:
            surface = self.main_surface
            actual_width = surface.canvas.winfo_width()
            actual_height = surface.canvas.winfo_height()
            width = actual_width if actual_width >= 100 else self.CANVAS_WIDTH
            height = actual_height if actual_height >= 100 else self.CANVAS_HEIGHT
            if actual_width >= 100 and actual_height >= 100:
                self._last_canvas_size = (actual_width, actual_height)
            surface.geometry = PreviewGeometry(self.original_frame.width, self.original_frame.height, width, height, surface.zoom)
            size = (max(1, round(self.original_frame.width * surface.geometry.scale)), max(1, round(self.original_frame.height * surface.geometry.scale)))
            surface.photo = ImageTk.PhotoImage(self.original_frame.resize(size, Image.Resampling.LANCZOS))
            surface.canvas.delete("all")
            surface.canvas.create_image(surface.geometry.offset_x + surface.pan_x, surface.geometry.offset_y + surface.pan_y, anchor="nw", image=surface.photo, tags="preview")
            surface.rectangle = [value + (surface.pan_x if index % 2 == 0 else surface.pan_y) for index, value in enumerate(surface.geometry.from_region(self.region))]
            self.preview_geometry = surface.geometry
            self.rectangle = surface.rectangle
            self._draw_surface(surface)
        finally:
            self._rendering_preview = False

    def _flush_zoom_render(self) -> None:
        self._zoom_render_pending = False
        self._zoom_after = None
        request = self._zoom_request
        self._zoom_request = None
        if not request:
            return
        surface, pointer_x, pointer_y, source_x, source_y = request
        if surface is self.preview_surface:
            self._render_large(restore_view=False, quality="interactive")
            if self.original_frame and self.preview_surface and self.preview_surface.geometry:
                canvas = self.preview_surface.canvas
                canvas.update_idletasks()
                width = self.preview_surface.geometry.canvas_width
                height = self.preview_surface.geometry.canvas_height
                origin_x = self.preview_surface.content_origin_x
                origin_y = self.preview_surface.content_origin_y
                viewport_w = max(1, canvas.winfo_width())
                viewport_h = max(1, canvas.winfo_height())
                scroll_width = max(width, viewport_w)
                scroll_height = max(height, viewport_h)
                target_x = origin_x + source_x * width - pointer_x
                target_y = origin_y + source_y * height - pointer_y
                max_x = max(0.0, float(scroll_width - viewport_w))
                max_y = max(0.0, float(scroll_height - viewport_h))
                if max_x <= 0:
                    canvas.xview_moveto(0.0)
                else:
                    target_x = max(0.0, min(max_x, target_x))
                    canvas.xview_moveto(target_x / max(1.0, float(scroll_width)))
                if max_y <= 0:
                    canvas.yview_moveto(0.0)
                else:
                    target_y = max(0.0, min(max_y, target_y))
                    canvas.yview_moveto(target_y / max(1.0, float(scroll_height)))
            self._schedule_large_quality_render()
        else:
            surface.zoom = max(0.5, min(4.0, surface.zoom))
            self._render_main()

    def _on_wheel(self, surface: PreviewSurface, event: tk.Event, direction: int = 0) -> str:
        step = direction or (1 if getattr(event, "delta", 0) > 0 else -1)
        current = self._zoom_value() if surface is self.preview_surface else surface.zoom
        current = current or 1.0
        factor = 1.06 if step > 0 else (1 / 1.06)
        new_value = max(0.5, min(4.0, current * factor))
        if surface is self.preview_surface:
            canvas = surface.canvas
            if not self._zoom_render_pending:
                canvas.update_idletasks()
            if surface.geometry and self.original_frame:
                old_width = max(1, surface.geometry.canvas_width)
                old_height = max(1, surface.geometry.canvas_height)
                source_x = max(0.0, min(1.0, (canvas.canvasx(event.x) - surface.content_origin_x) / old_width))
                source_y = max(0.0, min(1.0, (canvas.canvasy(event.y) - surface.content_origin_y) / old_height))
            else:
                source_x = source_y = 0.5
            self._set_preview_zoom(new_value, persist=False)
            if self._large_quality_after:
                try:
                    self.root.after_cancel(self._large_quality_after)
                except tk.TclError:
                    pass
                self._large_quality_after = None
            self._zoom_request = (surface, float(event.x), float(event.y), source_x, source_y)
        else:
            surface.zoom = new_value
            self._zoom_request = (surface, float(getattr(event, "x", 0)), float(getattr(event, "y", 0)), 0.5, 0.5)
        if not self._zoom_render_pending:
            self._zoom_render_pending = True
            self._zoom_after = self.root.after_idle(self._flush_zoom_render)
        self.schedule_persist()
        return "break"

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