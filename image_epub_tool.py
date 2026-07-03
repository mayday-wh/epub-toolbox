# -*- coding: utf-8 -*-
"""Tkinter GUI for converting image folders to EPUB comic books."""

from __future__ import annotations

import datetime as _dt
import ctypes
import html
import os
import re
import subprocess
import sys
import threading
import uuid
import zipfile
import tkinter as tk
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
APP_TITLE = "Epub工具箱"
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

BG = "#e6e8dd"
PANEL = "#f0f1e8"
FIELD = "#fbfbf4"
TEXT = "#263025"
MUTED = "#66705f"
GREEN = "#6d8263"
GREEN_DARK = "#5f7357"
BROWN = "#8a7a62"
BROWN_DARK = "#776850"
BLUE = "#6e8490"
BLUE_DARK = "#5f737e"
LINE = "#9aa28f"
TRACK = "#d7dccf"
BUTTON_TEXT = "#fff8ef"
DROP_FILL = "#e0ead7"
DROP_HOVER = "#edf4e7"
DROP_BORDER = GREEN

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_UI_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_SECTION = ("Microsoft YaHei UI", 11, "bold")
FONT_BUTTON = ("Microsoft YaHei UI", 10, "bold")
ACTION_BUTTON_WIDTH = 148
ACTION_BUTTON_HEIGHT = 46
ACTION_BUTTON_RADIUS = 12


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def scaled_window_size(root: Tk) -> tuple[int, int]:
    try:
        dpi_scale = float(root.tk.call("tk", "scaling")) / (96 / 72)
    except Exception:
        dpi_scale = 1.0

    dpi_ratio = max(1.0, dpi_scale / 1.25)
    resolution_ratio = max(
        1.0,
        min(root.winfo_screenwidth() / 2560, root.winfo_screenheight() / 1440),
    )
    scale = min(1.6, dpi_ratio, resolution_ratio)
    width = min(round(900 * scale), round(root.winfo_screenwidth() * 0.9))
    height = min(round(600 * scale), round(root.winfo_screenheight() * 0.9))
    return width, height


def rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class TkDndFolderDropTarget:
    def __init__(self, root: Tk, widgets: list[tk.Widget], on_drop) -> None:
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
    def __init__(self, master, text: str, variable: BooleanVar) -> None:
        super().__init__(
            master,
            bg=PANEL,
            cursor="hand2",
            highlightthickness=0,
            takefocus=True,
        )
        self.text = text
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
            font=FONT_UI,
            cursor="hand2",
        )
        self.label.pack(side=tk.LEFT, pady=5)

        self._trace_id = self.variable.trace_add("write", lambda *_args: self.draw())
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
        bg = "#fffdf8" if active else PANEL
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

        self.box.create_rectangle(
            3,
            3,
            19,
            19,
            fill=fill,
            outline=outline,
            width=2,
        )
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


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master,
        text: str,
        command,
        color: str,
        hover_color: str,
        parent_bg: str,
    ) -> None:
        super().__init__(
            master,
            width=ACTION_BUTTON_WIDTH,
            height=ACTION_BUTTON_HEIGHT,
            bg=parent_bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self.text = text
        self.command = command
        self.color = color
        self.hover_color = hover_color
        self.enabled = True
        self.hover = False

        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.bind("<Button-1>", self.invoke)
        self.bind("<space>", self.invoke)
        self.bind("<Return>", self.invoke)
        self.bind("<FocusIn>", lambda _event: self.draw())
        self.bind("<FocusOut>", lambda _event: self.draw())
        self.draw()

    def set_hover(self, active: bool) -> None:
        self.hover = active
        self.draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()

    def invoke(self, _event=None) -> str:
        if self.enabled and self.command is not None:
            self.command()
        return "break"

    def draw(self) -> None:
        self.delete("all")
        fill = TRACK if not self.enabled else (self.hover_color if self.hover else self.color)
        text_color = MUTED if not self.enabled else BUTTON_TEXT
        outline = BLUE_DARK if self.focus_get() is self and self.enabled else fill
        rounded_rect(
            self,
            1,
            1,
            ACTION_BUTTON_WIDTH - 1,
            ACTION_BUTTON_HEIGHT - 1,
            ACTION_BUTTON_RADIUS,
            fill=fill,
            outline=outline,
            width=1,
        )
        self.create_text(
            ACTION_BUTTON_WIDTH // 2,
            ACTION_BUTTON_HEIGHT // 2,
            text=self.text,
            fill=text_color,
            font=FONT_BUTTON,
        )


class RoundedDropBox(tk.Canvas):
    def __init__(self, master, title: str, hint: str, command, bg: str = PANEL) -> None:
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
        rounded_rect(self, 1, 1, width - 1, height - 1, ACTION_BUTTON_RADIUS, fill=fill, outline=DROP_BORDER, width=1)
        self.create_text(
            width // 2,
            height // 2 - 13,
            text=self.title,
            fill=TEXT,
            font=FONT_SECTION,
        )
        self.create_text(
            width // 2,
            height // 2 + 17,
            text=self.hint,
            fill=MUTED,
            font=FONT_SMALL,
        )


def natural_key(value: str) -> str:
    return re.sub(r"\d+", lambda m: m.group(0).zfill(20), value.lower())


def get_available_output_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def get_available_directory_path(path: Path) -> Path:
    if not path.exists():
        return path
    if path.is_dir() and not any(path.iterdir()):
        return path

    index = 2
    while True:
        candidate = path.with_name(f"{path.name} ({index})")
        if not candidate.exists():
            return candidate
        index += 1


def collect_images(input_dir: Path, recurse: bool) -> list[Path]:
    iterator = input_dir.rglob("*") if recurse else input_dir.iterdir()
    images = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(
        images,
        key=lambda path: natural_key(path.relative_to(input_dir).as_posix()),
    )


def extract_images_from_epub(input_epub: Path, output_dir: Path, progress) -> Path:
    input_epub = input_epub.resolve()
    if not input_epub.is_file():
        raise ValueError(f"找不到 EPUB 文件：{input_epub}")
    if input_epub.suffix.lower() != ".epub":
        raise ValueError("请选择 .epub 文件。")

    output_dir = get_available_directory_path(output_dir.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(input_epub, "r") as zip_file:
        image_entries = [
            info
            for info in zip_file.infolist()
            if not info.is_dir() and Path(info.filename).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        image_entries.sort(key=lambda info: natural_key(info.filename))

        if not image_entries:
            raise ValueError("这个 EPUB 中没有找到支持的图片。")

        for index, info in enumerate(image_entries, start=1):
            ext = Path(info.filename).suffix.lower()
            target = output_dir / f"{index:04d}{ext}"
            progress(f"正在提取第 {index} / {len(image_entries)} 张图片...")
            with zip_file.open(info, "r") as source, target.open("wb") as dest:
                dest.write(source.read())

    progress("图片提取完成")
    return output_dir


def write_text(zip_file: zipfile.ZipFile, name: str, text: str) -> None:
    zip_file.writestr(name, text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)


def create_epub(
    input_dir: Path,
    output_path: Path,
    title: str,
    author: str,
    language: str,
    rtl: bool,
    recurse: bool,
    no_overwrite: bool,
    page_fit: str,
    progress,
) -> Path:
    input_dir = input_dir.resolve()
    if not input_dir.is_dir():
        raise ValueError(f"找不到图片来源：{input_dir}")

    images = collect_images(input_dir, recurse)
    if not images:
        raise ValueError("没有找到支持的图片。支持格式：jpg, jpeg, png, gif, webp")

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if no_overwrite:
        output_path = get_available_output_path(output_path)
    elif output_path.exists():
        output_path.unlink()

    title = title.strip() or input_dir.name
    author = author.strip() or "Unknown"
    language = language.strip() or "zh-CN"
    progression = "rtl" if rtl else "ltr"

    escaped_title = html.escape(title, quote=True)
    escaped_author = html.escape(author, quote=True)
    escaped_language = html.escape(language, quote=True)
    identifier = f"urn:uuid:{uuid.uuid4()}"
    modified = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    image_css = (
        """img {
  display: block;
  width: 100%;
  height: auto;
  margin: 0 auto;
}
"""
        if page_fit == "Width"
        else """.page {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 100vh;
}
img {
  display: block;
  height: auto;
  margin: 0 auto;
  max-height: 100vh;
  max-width: 100%;
  width: auto;
}
"""
    )

    css = f"""html, body {{
  margin: 0;
  padding: 0;
  background: #fff;
}}
body {{
  text-align: center;
}}
.page {{
  margin: 0;
  padding: 0;
  page-break-after: always;
  break-after: page;
}}
{image_css}"""

    manifest_items = [
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '    <item id="css" href="styles/page.css" media-type="text/css"/>',
    ]
    spine_items: list[str] = []
    nav_items: list[str] = []
    ncx_items: list[str] = []

    with zipfile.ZipFile(output_path, "w", allowZip64=True) as zip_file:
        zip_file.writestr(
            "mimetype",
            b"application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )

        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        write_text(zip_file, "META-INF/container.xml", container_xml)
        write_text(zip_file, "OEBPS/styles/page.css", css)

        for index, image_path in enumerate(images, start=1):
            progress(f"正在添加第 {index} / {len(images)} 张图片...")
            ext = image_path.suffix.lower()
            image_name = f"page-{index:04d}{ext}"
            page_name = f"page-{index:04d}.xhtml"
            image_id = f"img{index:04d}"
            page_id = f"page{index:04d}"
            mime = MIME_TYPES.get(ext, "application/octet-stream")
            cover_property = ' properties="cover-image"' if index == 1 else ""

            zip_file.write(
                image_path,
                f"OEBPS/images/{image_name}",
                compress_type=zipfile.ZIP_STORED,
            )

            xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{escaped_language}">
<head>
  <title>{escaped_title} - Page {index}</title>
  <link rel="stylesheet" type="text/css" href="styles/page.css"/>
</head>
<body>
  <div class="page">
    <img src="images/{image_name}" alt="Page {index}"/>
  </div>
</body>
</html>
"""
            write_text(zip_file, f"OEBPS/{page_name}", xhtml)

            manifest_items.append(
                f'    <item id="{image_id}" href="images/{image_name}" media-type="{mime}"{cover_property}/>'
            )
            manifest_items.append(
                f'    <item id="{page_id}" href="{page_name}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'    <itemref idref="{page_id}"/>')
            nav_items.append(f'      <li><a href="{page_name}">Page {index}</a></li>')
            ncx_items.append(
                f"""    <navPoint id="navPoint-{index}" playOrder="{index}">
      <navLabel><text>Page {index}</text></navLabel>
      <content src="{page_name}"/>
    </navPoint>"""
            )

        content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{identifier}</dc:identifier>
    <dc:title>{escaped_title}</dc:title>
    <dc:creator>{escaped_author}</dc:creator>
    <dc:language>{escaped_language}</dc:language>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
{os.linesep.join(manifest_items)}
  </manifest>
  <spine toc="ncx" page-progression-direction="{progression}">
{os.linesep.join(spine_items)}
  </spine>
</package>
"""
        write_text(zip_file, "OEBPS/content.opf", content_opf)

        nav_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{escaped_title}</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{escaped_title}</h1>
    <ol>
{os.linesep.join(nav_items)}
    </ol>
  </nav>
</body>
</html>
"""
        write_text(zip_file, "OEBPS/nav.xhtml", nav_xhtml)

        toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{identifier}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escaped_title}</text></docTitle>
  <navMap>
{os.linesep.join(ncx_items)}
  </navMap>
</ncx>
"""
        write_text(zip_file, "OEBPS/toc.ncx", toc_ncx)

    progress("生成完成")
    return output_path


class ImageToEpubApp:
    def __init__(self, root: tk.Misc, embedded: bool = False) -> None:
        self.root = root
        self.embedded = embedded
        if not embedded and hasattr(self.root, "title"):
            self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        if not embedded and hasattr(self.root, "geometry"):
            width, height = scaled_window_size(root)
            self.root.geometry(f"{width}x{height}")
        if not embedded and hasattr(self.root, "minsize"):
            self.root.minsize(780, 520)
        self.root.option_add("*Font", FONT_UI)
        self._configure_style()

        self.input_dir = StringVar()
        self.input_epub = StringVar()
        self.output_path = StringVar()
        self.title = StringVar()
        self.author = StringVar(value="Unknown")
        self.language = StringVar(value="zh-CN")
        self.page_fit = StringVar(value="Contain")
        self.rtl = BooleanVar(value=False)
        self.recurse = BooleanVar(value=False)
        self.no_overwrite = BooleanVar(value=True)
        self.open_folder = BooleanVar(value=False)
        self.status = StringVar(value="请选择图片来源")

        self._build_ui()
        self.drop_target = TkDndFolderDropTarget(
            root,
            [self.drop_box],
            self.handle_dropped_paths,
        )
        if self.drop_target.enabled:
            self.drop_box.set_texts("拖入图片来源", "也可以点击这里选择文件夹")
        else:
            self.drop_box.set_texts("点击选择图片来源", "支持 jpg、png、gif、webp")

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", font=FONT_UI, foreground=TEXT)
        style.configure("App.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Status.TFrame", background=BG)
        style.configure("App.TLabel", background=PANEL, foreground=TEXT, font=FONT_UI)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)
        style.configure("App.TLabelframe", background=PANEL, bordercolor=LINE, relief="solid")
        style.configure(
            "App.TLabelframe.Label",
            background=PANEL,
            foreground=TEXT,
            font=FONT_SECTION,
        )
        style.configure(
            "App.TEntry",
            fieldbackground=FIELD,
            foreground=TEXT,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=(8, 5),
        )
        style.configure(
            "App.TCombobox",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            bordercolor=LINE,
            arrowcolor=TEXT,
            padding=(8, 5),
        )
        style.map("App.TCombobox", fieldbackground=[("readonly", FIELD)])
        style.configure(
            "App.TCheckbutton",
            background=PANEL,
            foreground=TEXT,
            font=FONT_UI,
            focuscolor=PANEL,
            padding=(4, 4),
        )
        style.map("App.TCheckbutton", foreground=[("disabled", MUTED)])
        style.configure(
            "Tool.TButton",
            background=BLUE,
            foreground=BUTTON_TEXT,
            borderwidth=0,
            focusthickness=0,
            font=FONT_BUTTON,
            padding=(14, 7),
        )
        style.map(
            "Tool.TButton",
            background=[("disabled", TRACK), ("active", BLUE_DARK), ("pressed", BLUE_DARK)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "Primary.TButton",
            background=GREEN,
            foreground=BUTTON_TEXT,
            borderwidth=0,
            focusthickness=0,
            font=FONT_BUTTON,
            padding=(20, 8),
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", TRACK), ("active", GREEN_DARK), ("pressed", GREEN_DARK)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "Secondary.TButton",
            background=BROWN,
            foreground=BUTTON_TEXT,
            borderwidth=0,
            focusthickness=0,
            font=FONT_BUTTON,
            padding=(14, 7),
        )
        style.map(
            "Secondary.TButton",
            background=[("disabled", TRACK), ("active", BROWN_DARK), ("pressed", BROWN_DARK)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "App.Horizontal.TProgressbar",
            background=GREEN,
            troughcolor=TRACK,
            bordercolor=LINE,
            lightcolor=GREEN,
            darkcolor=GREEN,
        )

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=18, style="App.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        file_panel = ttk.LabelFrame(frame, text="文件选择", padding=(14, 12), style="App.TLabelframe")
        file_panel.grid(row=0, column=0, sticky="ew")
        file_panel.columnconfigure(1, weight=1)

        self.drop_box = RoundedDropBox(
            file_panel,
            title="点击选择图片来源",
            hint="支持 jpg、png、gif、webp",
            command=self.choose_input_dir,
            bg=PANEL,
        )
        self.drop_box.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 16))

        ttk.Label(file_panel, text="图片来源", style="App.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(file_panel, textvariable=self.input_dir, style="App.TEntry").grid(
            row=1, column=1, sticky="ew", padx=10, pady=(4, 8)
        )
        RoundedButton(file_panel, "选择", self.choose_input_dir, BLUE, BLUE_DARK, PANEL).grid(
            row=1, column=2, pady=(4, 8)
        )

        ttk.Label(file_panel, text="待提取 EPUB", style="App.TLabel").grid(row=2, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(file_panel, textvariable=self.input_epub, style="App.TEntry").grid(
            row=2, column=1, sticky="ew", padx=10, pady=(4, 8)
        )
        RoundedButton(file_panel, "选择", self.choose_input_epub, BLUE, BLUE_DARK, PANEL).grid(
            row=2, column=2, pady=(4, 8)
        )

        ttk.Label(file_panel, text="保存为 EPUB", style="App.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(file_panel, textvariable=self.output_path, style="App.TEntry").grid(
            row=3, column=1, sticky="ew", padx=10, pady=(4, 8)
        )
        RoundedButton(file_panel, "选择", self.choose_output_path, BLUE, BLUE_DARK, PANEL).grid(
            row=3, column=2, pady=(4, 8)
        )

        body = ttk.Frame(frame, style="App.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        info_panel = ttk.LabelFrame(body, text="书籍信息", padding=(14, 12), style="App.TLabelframe")
        info_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        info_panel.columnconfigure(1, weight=1)

        ttk.Label(info_panel, text="书名", style="App.TLabel").grid(row=0, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(info_panel, textvariable=self.title, style="App.TEntry").grid(
            row=0, column=1, sticky="ew", padx=(10, 0), pady=(4, 8)
        )

        ttk.Label(info_panel, text="作者", style="App.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(info_panel, textvariable=self.author, style="App.TEntry").grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 8)
        )

        ttk.Label(info_panel, text="语言", style="App.TLabel").grid(row=2, column=0, sticky="w", pady=(4, 8))
        ttk.Entry(info_panel, textvariable=self.language, style="App.TEntry").grid(
            row=2, column=1, sticky="ew", padx=(10, 0), pady=(4, 8)
        )

        ttk.Label(info_panel, text="显示方式", style="App.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 8))
        fit_box = ttk.Combobox(
            info_panel,
            textvariable=self.page_fit,
            values=("Contain", "Width"),
            state="readonly",
            style="App.TCombobox",
            width=12,
        )
        fit_box.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(4, 8))

        options = ttk.LabelFrame(body, text="选项", padding=(14, 9), style="App.TLabelframe")
        options.grid(row=0, column=1, sticky="nsew")
        options.columnconfigure(0, weight=1)
        DrawnCheckOption(options, "右到左翻页", self.rtl).grid(row=0, column=0, sticky="w", pady=2)
        DrawnCheckOption(options, "包含子文件夹", self.recurse).grid(row=1, column=0, sticky="w", pady=2)
        DrawnCheckOption(options, "保留已有文件", self.no_overwrite).grid(row=2, column=0, sticky="w", pady=2)
        DrawnCheckOption(options, "完成后打开目录", self.open_folder).grid(row=3, column=0, sticky="w", pady=2)

        status_panel = ttk.Frame(frame, style="Status.TFrame")
        status_panel.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        status_panel.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(status_panel, mode="indeterminate", style="App.Horizontal.TProgressbar")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 14))

        self.extract_button = RoundedButton(status_panel, "提取图片", self.extract_images, BROWN, BROWN_DARK, BG)
        self.extract_button.grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.generate_button = RoundedButton(status_panel, "生成书籍", self.generate, GREEN, GREEN_DARK, BG)
        self.generate_button.grid(row=0, column=2, sticky="e")

    def choose_input_dir(self) -> None:
        folder = filedialog.askdirectory(title="选择图片来源")
        if not folder:
            return

        self.set_input_dir(Path(folder))

    def handle_dropped_paths(self, paths: list[str]) -> None:
        for path_text in paths:
            folder_path = Path(path_text)
            if folder_path.is_dir():
                self.set_input_dir(folder_path)
                return

            messagebox.showwarning(APP_TITLE, "请拖入图片来源文件夹。")

    def set_input_dir(self, folder_path: Path) -> None:
        if not folder_path.is_dir():
            return

        folder_path = folder_path.resolve()
        self.input_dir.set(str(folder_path))
        if not self.title.get().strip():
            self.title.set(folder_path.name)
        if not self.output_path.get().strip():
            self.output_path.set(str(folder_path.with_suffix(".epub")))
        self.status.set("已选择图片来源")

    def choose_input_epub(self) -> None:
        path = filedialog.askopenfilename(
            title="选择待提取 EPUB",
            filetypes=[("EPUB files", "*.epub")],
        )
        if path:
            self.set_input_epub(Path(path))

    def set_input_epub(self, epub_path: Path) -> None:
        if not epub_path.is_file():
            return

        epub_path = epub_path.resolve()
        self.input_epub.set(str(epub_path))
        if not self.input_dir.get().strip():
            self.input_dir.set(str(epub_path.with_name(f"{epub_path.stem}_images")))
        if not self.title.get().strip():
            self.title.set(epub_path.stem)
        if not self.output_path.get().strip():
            self.output_path.set(str(epub_path.with_name(f"{epub_path.stem}_new.epub")))
        self.status.set("已选择待提取 EPUB")

    def choose_output_path(self) -> None:
        initial_dir = None
        if self.input_dir.get().strip():
            initial_dir = str(Path(self.input_dir.get()).parent)

        path = filedialog.asksaveasfilename(
            title="选择 EPUB 保存位置",
            defaultextension=".epub",
            filetypes=[("EPUB files", "*.epub")],
            initialdir=initial_dir,
            initialfile=(self.title.get().strip() or "book") + ".epub",
        )
        if path:
            self.output_path.set(path)

    def set_busy(self, busy: bool) -> None:
        self.generate_button.set_enabled(not busy)
        self.extract_button.set_enabled(not busy)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def set_status(self, text: str) -> None:
        self.root.after(0, self.status.set, text)

    def extract_images(self) -> None:
        input_epub_text = self.input_epub.get().strip()
        if not input_epub_text:
            messagebox.showwarning(APP_TITLE, "请先选择待提取的 EPUB 文件。")
            return

        output_dir_text = self.input_dir.get().strip()
        if output_dir_text:
            output_dir = Path(output_dir_text)
        else:
            epub_path = Path(input_epub_text)
            output_dir = epub_path.with_name(f"{epub_path.stem}_images")
            self.input_dir.set(str(output_dir))

        output_dir_target = output_dir
        self.set_busy(True)
        self.status.set("正在提取图片...")

        def worker() -> None:
            try:
                output_dir = extract_images_from_epub(
                    input_epub=Path(input_epub_text),
                    output_dir=output_dir_target,
                    progress=self.set_status,
                )
                self.root.after(0, self.on_extract_success, output_dir)
            except Exception as exc:  # noqa: BLE001 - GUI should report friendly errors.
                self.root.after(0, self.on_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def generate(self) -> None:
        input_text = self.input_dir.get().strip()
        output_text = self.output_path.get().strip()
        if not input_text:
            messagebox.showwarning(APP_TITLE, "请先选择图片来源。")
            return
        if not output_text:
            messagebox.showwarning(APP_TITLE, "请先选择 EPUB 保存位置。")
            return

        self.set_busy(True)
        self.status.set("正在生成书籍...")

        def worker() -> None:
            try:
                output = create_epub(
                    input_dir=Path(input_text),
                    output_path=Path(output_text),
                    title=self.title.get(),
                    author=self.author.get(),
                    language=self.language.get(),
                    rtl=self.rtl.get(),
                    recurse=self.recurse.get(),
                    no_overwrite=self.no_overwrite.get(),
                    page_fit=self.page_fit.get(),
                    progress=self.set_status,
                )
                self.root.after(0, self.on_success, output)
            except Exception as exc:  # noqa: BLE001 - GUI should report friendly errors.
                self.root.after(0, self.on_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def on_success(self, output: Path) -> None:
        self.set_busy(False)
        self.output_path.set(str(output))
        self.status.set("书籍生成完成")
        if self.open_folder.get():
            subprocess.Popen(["explorer", str(output.parent)])
        messagebox.showinfo(APP_TITLE, f"书籍生成完成：\n\n{output}")

    def on_extract_success(self, output_dir: Path) -> None:
        self.set_busy(False)
        self.input_dir.set(str(output_dir))
        self.status.set("图片提取完成")
        if self.open_folder.get():
            subprocess.Popen(["explorer", str(output_dir)])
        messagebox.showinfo(APP_TITLE, f"图片提取完成：\n\n{output_dir}")

    def on_error(self, message: str) -> None:
        self.set_busy(False)
        self.status.set("操作失败")
        messagebox.showerror(APP_TITLE, message)


def main() -> None:
    enable_dpi_awareness()
    root = Tk()
    app = ImageToEpubApp(root)
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        if input_path.is_file() and input_path.suffix.lower() == ".epub":
            app.set_input_epub(input_path)
        else:
            app.set_input_dir(input_path)
    root.mainloop()


if __name__ == "__main__":
    main()
