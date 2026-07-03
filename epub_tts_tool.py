from __future__ import annotations

import asyncio
import queue
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk
import tkinter.font as tkfont

from epub_tts import (
    Chapter,
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    MAX_TTS_CHARS,
    concat_mp3_with_ffmpeg,
    parse_epub,
    safe_filename,
    split_text,
    stream_tts_chunk,
    write_text_preview,
)


BG = "#e6e8dd"
BAR = "#cfd8c6"
PANEL = "#f0f1e8"
FIELD = "#fbfbf4"
CARD = "#fffdf8"
TEXT = "#263025"
MUTED = "#66705f"
GREEN = "#6d8263"
GREEN_DARK = "#5b704f"
BROWN = "#8a7a62"
BROWN_DARK = "#756750"
BLUE = "#6e8490"
BLUE_DARK = "#5d737f"
RED = "#9a5f58"
LINE = "#9aa28f"
SELECTED = "#d8e5d1"
BUTTON_TEXT = "#fff8ef"
DROP_FILL = "#e0ead7"
DROP_HOVER = "#edf4e7"
DROP_BORDER = GREEN

APP_TITLE = "Epub工具箱"

VOICE_OPTIONS = [
    ("云扬 男声 - 稳重", "zh-CN-YunyangNeural"),
    ("云希 男声 - 轻快", "zh-CN-YunxiNeural"),
    ("云健 男声 - 清晰", "zh-CN-YunjianNeural"),
    ("云夏 男声 - 年轻", "zh-CN-YunxiaNeural"),
    ("晓晓 女声 - 自然", "zh-CN-XiaoxiaoNeural"),
    ("晓伊 女声 - 温和", "zh-CN-XiaoyiNeural"),
]


class TkDndFileDropTarget:
    def __init__(self, root: tk.Misc, widgets: list[tk.Widget], on_drop) -> None:
        self.root = root
        self.on_drop = on_drop
        self.enabled = False

        try:
            root.tk.call("package", "require", "tkdnd")
            command = root.register(self._handle_drop)
            for widget in widgets:
                root.tk.call("tkdnd::drop_target", "register", widget._w, "DND_Files")
                root.tk.call("bind", widget._w, "<<Drop>>", f"{command} %D")
            self.enabled = True
        except Exception:
            self.enabled = False

    def _handle_drop(self, data: str) -> str:
        try:
            paths = list(self.root.tk.splitlist(data))
        except Exception:
            paths = [data] if data else []
        self.root.after(0, self.on_drop, paths)
        return "break"


class DrawnCheckOption(tk.Frame):
    def __init__(self, master: tk.Misc, text: str, variable: BooleanVar) -> None:
        super().__init__(
            master,
            bg=PANEL,
            cursor="hand2",
            highlightthickness=0,
            takefocus=True,
        )
        self.variable = variable
        self.hover = False

        self.box = tk.Canvas(
            self,
            width=22,
            height=22,
            bg=PANEL,
            bd=0,
            cursor="hand2",
            highlightthickness=0,
        )
        self.box.pack(side=tk.LEFT, padx=(2, 9), pady=5)
        self.label = tk.Label(
            self,
            text=text,
            bg=PANEL,
            fg=TEXT,
            font=("微软雅黑", 10),
            cursor="hand2",
        )
        self.label.pack(side=tk.LEFT, pady=5)

        self.variable.trace_add("write", lambda *_args: self.draw())
        for widget in (self, self.box, self.label):
            widget.bind("<Button-1>", self.toggle)
            widget.bind("<Enter>", lambda _event: self.set_hover(True))
            widget.bind("<Leave>", lambda _event: self.set_hover(False))
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<FocusIn>", lambda _event: self.draw())
        self.bind("<FocusOut>", lambda _event: self.draw())
        self.draw()

    def set_hover(self, active: bool) -> None:
        self.hover = active
        bg = CARD if active else PANEL
        self.configure(bg=bg)
        self.box.configure(bg=bg)
        self.label.configure(bg=bg)
        self.draw()

    def toggle(self, _event=None) -> str:
        self.variable.set(not self.variable.get())
        return "break"

    def draw(self) -> None:
        self.box.delete("all")
        checked = self.variable.get()
        fill = GREEN if checked else FIELD
        outline = GREEN_DARK if checked else LINE
        if self.focus_get() is self:
            outline = BLUE_DARK

        self.box.create_rectangle(3, 3, 19, 19, fill=fill, outline=outline, width=2)
        if checked:
            self.box.create_line(
                7,
                11,
                10,
                15,
                16,
                7,
                fill=BUTTON_TEXT,
                width=3,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )


def rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs):
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command,
        color: str = GREEN,
        hover_color: str = GREEN_DARK,
        text_color: str = BUTTON_TEXT,
        bg: str = BAR,
        width: int | None = None,
        padx: int = 16,
        pady: int = 8,
        radius: int = 12,
    ) -> None:
        self.text = text
        self.command = command
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.bg = bg
        self.radius = radius
        self.enabled = True
        self.font_obj = ("微软雅黑", 10, "bold")

        measure = tkfont.Font(family="微软雅黑", size=10, weight="bold")
        self.width = width or measure.measure(text) + padx * 2
        self.height = measure.metrics("linespace") + pady * 2
        self.current_color = color

        super().__init__(
            parent,
            width=self.width,
            height=self.height,
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.draw()
        self.bind("<Enter>", lambda _event: self.set_color(self.hover_color))
        self.bind("<Leave>", lambda _event: self.set_color(self.color))
        self.bind("<Button-1>", lambda _event: self.invoke())

    def draw(self) -> None:
        self.delete("all")
        fill = self.current_color if self.enabled else "#b8c1ad"
        text_color = self.text_color if self.enabled else MUTED
        rounded_rect(self, 1, 1, self.width - 1, self.height - 1, self.radius, fill=fill, outline=fill)
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=text_color, font=self.font_obj)

    def set_color(self, color: str) -> None:
        if self.enabled:
            self.current_color = color
            self.draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.current_color = self.color
        self.draw()

    def invoke(self) -> None:
        if self.enabled and self.command:
            self.command()


class RoundedDropBox(tk.Canvas):
    def __init__(self, master: tk.Misc, title: str, hint: str, command, bg: str = PANEL) -> None:
        super().__init__(
            master,
            height=136,
            bg=bg,
            bd=0,
            cursor="hand2",
            highlightthickness=0,
        )
        self.title = title
        self.hint = hint
        self.command = command
        self.hover = False
        self.bind("<Configure>", lambda _event: self.draw())
        self.bind("<Button-1>", lambda _event: self.command())
        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.draw()

    def set_texts(self, title: str, hint: str) -> None:
        self.title = title
        self.hint = hint
        self.draw()

    def set_hover(self, active: bool) -> None:
        self.hover = active
        self.draw()

    def draw(self) -> None:
        width = max(self.winfo_width(), 240)
        height = max(self.winfo_height(), 136)
        fill = DROP_HOVER if self.hover else DROP_FILL
        self.delete("all")
        rounded_rect(self, 1, 1, width - 1, height - 1, 12, fill=fill, outline=DROP_BORDER, width=1)
        self.create_text(
            width // 2,
            height // 2 - 13,
            text=self.title,
            fill=TEXT,
            font=("微软雅黑", 12, "bold"),
        )
        self.create_text(
            width // 2,
            height // 2 + 17,
            text=self.hint,
            fill=MUTED,
            font=("微软雅黑", 10),
        )


class EpubTtsToolApp:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.epub_path: Path | None = None
        self.book_title = ""
        self.chapters: list[Chapter] = []
        self.checked: set[int] = set()
        self.is_working = False
        self.worker_failed = False

        self.voice_var = StringVar(value=VOICE_OPTIONS[0][1])
        self.rate_var = StringVar(value=DEFAULT_RATE)
        self.pitch_var = StringVar(value=DEFAULT_PITCH)
        self.volume_var = StringVar(value=DEFAULT_VOLUME)
        self.output_var = StringVar()
        self.merge_var = BooleanVar(value=False)
        self.overwrite_var = BooleanVar(value=False)
        self.status_var = StringVar(value="请选择 EPUB 文件")
        self.selection_var = StringVar(value="未读取章节")
        self.progress_var = tk.DoubleVar(value=0)

        self._configure_style()
        self._build_ui()
        self.drop_target = TkDndFileDropTarget(self.root, [self.drop_box], self.handle_dropped_paths)
        if self.drop_target.enabled:
            self.drop_box.set_texts("拖入 EPUB", "也可以点击选择书籍")
        else:
            self.drop_box.set_texts("点击选择书籍", "请选择 .epub 文件")
        self.root.after(120, self._poll_messages)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Tts.TFrame", background=BG)
        style.configure("TtsPanel.TFrame", background=PANEL)
        style.configure("TtsTitle.TLabel", background=PANEL, foreground=TEXT, font=("微软雅黑", 13, "bold"))
        style.configure("TtsHint.TLabel", background=PANEL, foreground=MUTED, font=("微软雅黑", 10))
        style.configure("TtsStatus.TLabel", background=BG, foreground=MUTED, font=("微软雅黑", 10))
        style.configure("Tts.TEntry", padding=(7, 5), fieldbackground=FIELD, foreground=TEXT)
        style.configure("Tts.TCombobox", padding=(7, 5), fieldbackground=FIELD, foreground=TEXT)
        style.map("Tts.TCombobox", fieldbackground=[("readonly", FIELD)])
        style.configure(
            "Tts.Treeview",
            background=FIELD,
            fieldbackground=FIELD,
            foreground=TEXT,
            font=("微软雅黑", 10),
            rowheight=34,
        )
        style.configure(
            "Tts.Treeview.Heading",
            background=BAR,
            foreground=TEXT,
            font=("微软雅黑", 10, "bold"),
            padding=(6, 7),
        )
        style.map("Tts.Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
        style.configure("Tts.Horizontal.TProgressbar", background=GREEN, troughcolor="#d7dccf")
    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=(20, 16, 20, 14), style="Tts.TFrame")
        shell.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        top = tk.Frame(shell, bg=BAR, highlightthickness=1, highlightbackground=LINE)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top.columnconfigure(1, weight=1)

        actions = tk.Frame(top, bg=BAR)
        actions.grid(row=0, column=0, sticky="w", padx=14, pady=10)
        RoundedButton(actions, "选择书籍", self.choose_epub, BLUE, BLUE_DARK, bg=BAR).pack(
            side="left", padx=(0, 8)
        )
        RoundedButton(actions, "保存目录", self.choose_output, BLUE, BLUE_DARK, bg=BAR).pack(
            side="left", padx=(0, 8)
        )
        RoundedButton(actions, "全选", self.select_all, CARD, FIELD, text_color=TEXT, bg=BAR).pack(
            side="left", padx=(10, 8)
        )
        RoundedButton(actions, "取消全选", self.select_none, CARD, FIELD, text_color=TEXT, bg=BAR).pack(
            side="left", padx=(0, 8)
        )
        RoundedButton(actions, "智能选择", self.select_body_guess, BROWN, BROWN_DARK, bg=BAR).pack(side="left")

        self.export_button = RoundedButton(top, "导出语音", self.export_mp3, GREEN, GREEN_DARK, bg=BAR)
        self.export_button.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        body = ttk.Frame(shell, style="Tts.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=330)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = self._panel(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="语音导出", style="TtsTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.drop_box = RoundedDropBox(
            left,
            title="拖入 EPUB",
            hint="或点击选择书籍",
            command=self.choose_epub,
            bg=PANEL,
        )
        self.drop_box.grid(row=1, column=0, sticky="ew", pady=(12, 16))

        self.file_label = tk.Label(
            left,
            text="尚未选择书籍",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=290,
            font=("微软雅黑", 10),
        )
        self.file_label.grid(row=2, column=0, sticky="ew", pady=(0, 18))

        ttk.Label(left, text="保存目录", style="TtsTitle.TLabel").grid(row=3, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(left, textvariable=self.output_var, style="Tts.TEntry").grid(row=4, column=0, sticky="ew", pady=(0, 18))

        ttk.Label(left, text="音色", style="TtsTitle.TLabel").grid(row=5, column=0, sticky="w", pady=(0, 8))
        self.voice_box = ttk.Combobox(
            left,
            textvariable=self.voice_var,
            values=[f"{label} | {value}" for label, value in VOICE_OPTIONS],
            state="readonly",
            style="Tts.TCombobox",
        )
        self.voice_box.grid(row=6, column=0, sticky="ew", pady=(0, 18))
        self.voice_box.current(0)

        params = ttk.Frame(left, style="TtsPanel.TFrame")
        params.grid(row=7, column=0, sticky="ew", pady=(0, 16))
        params.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(
            (("语速", self.rate_var), ("音调", self.pitch_var), ("音量", self.volume_var))
        ):
            ttk.Label(params, text=label, style="TtsHint.TLabel").grid(row=row, column=0, sticky="w", pady=(0, 10))
            ttk.Entry(params, textvariable=variable, width=10, style="Tts.TEntry").grid(
                row=row,
                column=1,
                sticky="ew",
                padx=(12, 0),
                pady=(0, 10),
            )

        DrawnCheckOption(left, "合并为整本音频", self.merge_var).grid(row=8, column=0, sticky="ew", pady=(2, 8))
        DrawnCheckOption(left, "覆盖已有音频", self.overwrite_var).grid(row=9, column=0, sticky="ew", pady=(0, 8))

        right = self._panel(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        ttk.Label(right, text="章节选择", style="TtsTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(right, textvariable=self.selection_var, style="TtsHint.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 8))

        table = tk.Frame(right, bg=PANEL)
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)

        columns = ("use", "index", "title")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse", style="Tts.Treeview")
        self.tree.heading("use", text="选")
        self.tree.heading("index", text="#")
        self.tree.heading("title", text="章节")
        self.tree.column("use", width=52, minwidth=52, anchor="center", stretch=False)
        self.tree.column("index", width=68, minwidth=68, anchor="center", stretch=False)
        self.tree.column("title", width=420, minwidth=220, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self._tree_clicked)
        self.tree.bind("<space>", self._toggle_selected_event)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure("checked", background=SELECTED)
        self.tree.tag_configure("odd", background="#f7f7ef")
        self.tree.tag_configure("even", background=FIELD)

        bottom = ttk.Frame(shell, style="Tts.TFrame")
        bottom.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        ttk.Progressbar(
            bottom,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            style="Tts.Horizontal.TProgressbar",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(bottom, textvariable=self.status_var, style="TtsStatus.TLabel").grid(row=0, column=1, sticky="e")

    def _panel(self, parent: tk.Misc) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PANEL,
            padx=16,
            pady=14,
            highlightthickness=1,
            highlightbackground=LINE,
        )

    def choose_epub(self) -> None:
        if self.is_working:
            messagebox.showinfo(APP_TITLE, "当前任务还没结束。")
            return
        file_name = filedialog.askopenfilename(title="选择书籍", filetypes=[("EPUB 文件", "*.epub"), ("所有文件", "*.*")])
        if file_name:
            self.load_epub(Path(file_name))

    def handle_dropped_paths(self, paths: list[str]) -> None:
        if self.is_working:
            messagebox.showinfo(APP_TITLE, "当前任务还没结束。")
            return

        for path_text in paths:
            epub_path = Path(path_text)
            if epub_path.is_file() and epub_path.suffix.lower() == ".epub":
                self.load_epub(epub_path)
                return

        messagebox.showwarning(APP_TITLE, "请拖入 EPUB 文件。")

    def choose_output(self) -> None:
        if self.is_working:
            messagebox.showinfo(APP_TITLE, "当前任务还没结束。")
            return
        folder = filedialog.askdirectory(title="选择保存目录")
        if folder:
            self.output_var.set(folder)

    def load_epub(self, path: Path) -> None:
        if path.suffix.lower() != ".epub":
            messagebox.showerror(APP_TITLE, "请选择 .epub 文件。")
            return
        self._start_worker(self._load_epub_worker, path)

    def _load_epub_worker(self, path: Path) -> None:
        self.message_queue.put(("status", "正在读取 EPUB..."))
        book = parse_epub(path, min_chars=30)
        output_dir = path.with_suffix("")
        output_dir.mkdir(parents=True, exist_ok=True)
        write_text_preview(book, output_dir)
        self.message_queue.put(("loaded", (path, book.title, book.chapters, output_dir)))

    def _render_chapters(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, chapter in enumerate(self.chapters, start=1):
            item_index = index - 1
            mark = "√" if item_index in self.checked else ""
            tags = ("checked",) if item_index in self.checked else ("odd" if index % 2 else "even",)
            self.tree.insert("", "end", iid=str(item_index), values=(mark, f"{index:03d}", chapter.title), tags=tags)

    def _tree_clicked(self, event: tk.Event) -> None:
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self._toggle_index(int(row_id))

    def _toggle_selected_event(self, _event: object | None = None) -> str:
        selected = self.tree.selection()
        if selected:
            self._toggle_index(int(selected[0]))
        return "break"

    def _toggle_index(self, index: int) -> None:
        if self.is_working:
            return
        if index in self.checked:
            self.checked.remove(index)
        else:
            self.checked.add(index)
        self._render_chapters()
        self.tree.selection_set(str(index))
        self._update_selected_status()

    def select_all(self) -> None:
        if self.is_working:
            return
        self.checked = set(range(len(self.chapters)))
        self._render_chapters()
        self._update_selected_status()

    def select_none(self) -> None:
        if self.is_working:
            return
        self.checked.clear()
        self._render_chapters()
        self._update_selected_status()

    def select_body_guess(self) -> None:
        if self.is_working:
            return
        self.checked = self._body_guess_indices()
        self._render_chapters()
        self._update_selected_status()

    def _body_guess_indices(self) -> set[int]:
        skip_words = ("版权", "目录", "制作声明", "附录", "封面")
        selected = set()
        for index, chapter in enumerate(self.chapters):
            if len(chapter.text) < 500:
                continue
            if any(word in chapter.title for word in skip_words):
                continue
            selected.add(index)
        return selected or set(range(len(self.chapters)))

    def selected_chapters(self) -> list[tuple[int, Chapter]]:
        return [(index, self.chapters[index]) for index in sorted(self.checked)]

    def export_mp3(self) -> None:
        if self.is_working:
            return
        selected = self.selected_chapters()
        if not selected:
            messagebox.showinfo(APP_TITLE, "请至少选择一个章节。")
            return
        if self.epub_path is None:
            messagebox.showinfo(APP_TITLE, "请先选择书籍。")
            return
        output_dir = Path(self.output_var.get() or self.epub_path.with_suffix(""))
        settings = {
            "voice": self._current_voice(),
            "rate": self.rate_var.get(),
            "pitch": self.pitch_var.get(),
            "volume": self.volume_var.get(),
            "overwrite": self.overwrite_var.get(),
        }
        self._start_worker(self._export_worker, selected, output_dir, self.merge_var.get(), settings)

    def _current_voice(self) -> str:
        value = self.voice_var.get()
        if "|" in value:
            return value.split("|", 1)[1].strip()
        return value.strip()

    def _start_worker(self, func, *args) -> None:
        self.is_working = True
        self.worker_failed = False
        self.export_button.set_enabled(False)
        self.progress_var.set(0)
        thread = threading.Thread(target=self._worker_wrapper, args=(func, args), daemon=True)
        thread.start()

    def _worker_wrapper(self, func, args: tuple[object, ...]) -> None:
        try:
            func(*args)
        except ImportError as exc:
            self.worker_failed = True
            self.message_queue.put(("error", f"缺少语音依赖：{exc}\n请先安装 edge-tts。"))
        except Exception as exc:
            self.worker_failed = True
            self.message_queue.put(("error", exc))
        finally:
            self.message_queue.put(("done", None))

    def _export_worker(
        self,
        selected: list[tuple[int, Chapter]],
        output_dir: Path,
        merge: bool,
        settings: dict[str, object],
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        chapters_dir = output_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        write_text_preview_from_selection(self.book_title, [chapter for _, chapter in selected], output_dir)

        chapter_files: list[Path] = []
        total_units = sum(max(1, len(split_text(chapter.text, MAX_TTS_CHARS))) for _, chapter in selected)
        finished_units = 0

        async def run() -> None:
            nonlocal finished_units
            for visible_index, (_original_index, chapter) in enumerate(selected, start=1):
                file_name = safe_filename(f"{visible_index:03d} {chapter.title}", fallback=f"{visible_index:03d}") + ".mp3"
                mp3_path = chapters_dir / file_name
                chapter_files.append(mp3_path)

                chunks = split_text(chapter.text, MAX_TTS_CHARS)
                if mp3_path.exists() and not settings["overwrite"]:
                    finished_units += max(1, len(chunks))
                    self.message_queue.put(("progress", (finished_units, total_units, f"跳过：{mp3_path.name}")))
                    continue

                self.message_queue.put(("status", f"正在导出 {visible_index}/{len(selected)}：{chapter.title}"))
                temp_path = mp3_path.with_name(mp3_path.name + ".part")
                try:
                    with temp_path.open("wb") as out:
                        for chunk_index, chunk in enumerate(chunks, start=1):
                            await stream_tts_chunk(
                                chunk,
                                out,
                                str(settings["voice"]),
                                str(settings["rate"]),
                                str(settings["pitch"]),
                                str(settings["volume"]),
                            )
                            finished_units += 1
                            label = f"{chapter.title} ({chunk_index}/{len(chunks)})"
                            self.message_queue.put(("progress", (finished_units, total_units, label)))
                    temp_path.replace(mp3_path)
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    raise

        asyncio.run(run())

        playlist = output_dir / "chapters.m3u"
        with playlist.open("w", encoding="utf-8") as f:
            for file in chapter_files:
                f.write(file.resolve().as_posix() + "\n")

        if merge and self.book_title:
            merged = output_dir / (safe_filename(self.book_title, "book") + ".mp3")
            if concat_mp3_with_ffmpeg(chapter_files, merged):
                self.message_queue.put(("status", f"导出完成：{merged}"))
            else:
                self.message_queue.put(("status", "章节音频已完成；未找到 ffmpeg，已跳过整本合并。"))
        else:
            self.message_queue.put(("status", f"导出完成：{output_dir}"))

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.message_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "status":
                self.status_var.set(str(payload))
            elif kind == "progress":
                done, total, label = payload  # type: ignore[misc]
                percent = (done / total * 100) if total else 0
                self.progress_var.set(percent)
                self.status_var.set(str(label))
            elif kind == "loaded":
                path, title, chapters, output_dir = payload  # type: ignore[misc]
                self.epub_path = path
                self.book_title = title
                self.chapters = chapters
                self.output_var.set(str(output_dir))
                self.file_label.configure(text=str(path), fg=TEXT)
                self.drop_box.set_texts(title, "拖入或点击可重新选择")
                self.checked = self._body_guess_indices()
                self._render_chapters()
                self.selection_var.set(f"已选择 {len(self.checked)} / {len(self.chapters)} 个章节")
                self.status_var.set(f"已读取：{title}，共 {len(chapters)} 个章节。")
            elif kind == "error":
                self.worker_failed = True
                self.status_var.set("发生错误。")
                messagebox.showerror(APP_TITLE, str(payload))
            elif kind == "done":
                self.is_working = False
                self.export_button.set_enabled(True)
                if self.progress_var.get() > 0 and not self.worker_failed:
                    self.progress_var.set(100)

        self.root.after(120, self._poll_messages)

    def _update_selected_status(self) -> None:
        self.selection_var.set(f"已选择 {len(self.checked)} / {len(self.chapters)} 个章节")
        self.status_var.set(f"已选择 {len(self.checked)} / {len(self.chapters)} 个章节。")


def write_text_preview_from_selection(title: str, chapters: list[Chapter], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / "book_text_preview.txt"
    with preview_path.open("w", encoding="utf-8") as f:
        f.write(title + "\n\n")
        for i, chapter in enumerate(chapters, start=1):
            f.write(f"## {i:03d} {chapter.title}\n")
            f.write(f"Source: {chapter.source}\n\n")
            f.write(chapter.text[:2000])
            f.write("\n\n")
    return preview_path
