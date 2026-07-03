import html
import json
import os
import re
import sys
import tkinter as tk
from tkinter import font, messagebox, ttk

from epub_tts_tool import EpubTtsToolApp
from image_epub_tool import ImageToEpubApp

try:
    from tkinterdnd2 import TkinterDnD
except Exception:
    TkinterDnD = None


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
BUTTON_TEXT = "#fff8ef"
CODE_BG = "#1f2a2d"
CODE_FG = "#eef4ea"
SELECTED = "#d8e5d1"

APP_BG = BG
PANEL_BG = PANEL
BORDER = LINE
TEXT_FG = TEXT
MUTED_FG = MUTED
PRIMARY = GREEN
PRIMARY_DARK = GREEN_DARK

PAGE_SIZES = {
    "small": (900, 600),
    "medium": (1000, 680),
    "large": (1200, 800),
}

UI_SCALE = 1.0


def enable_dpi_awareness():
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def create_root():
    if TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except Exception:
            pass
    return tk.Tk()


def detect_layout_scale(root):
    try:
        dpi_scale = float(root.tk.call("tk", "scaling")) / (96 / 72)
    except Exception:
        dpi_scale = 1.0

    dpi_ratio = max(1.0, dpi_scale / 1.25)
    resolution_ratio = max(
        1.0,
        min(root.winfo_screenwidth() / 2560, root.winfo_screenheight() / 1440),
    )
    return min(1.8, dpi_ratio, resolution_ratio)


def scaled_window_size(root, page="large", max_screen_ratio=0.9):
    scale = detect_layout_scale(root)
    base_w, base_h = PAGE_SIZES[page]
    width = min(round(base_w * scale), round(root.winfo_screenwidth() * max_screen_ratio))
    height = min(round(base_h * scale), round(root.winfo_screenheight() * max_screen_ratio))
    return width, height, scale


def sx(value):
    scaled = int(round(value * UI_SCALE))
    if value > 0:
        return max(1, scaled)
    if value < 0:
        return min(-1, scaled)
    return 0


def sp(values):
    return tuple(sx(v) for v in values)


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
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
        parent,
        text,
        command,
        color=GREEN,
        hover_color=GREEN_DARK,
        text_color=BUTTON_TEXT,
        bg=BAR,
        padx=16,
        pady=8,
        radius=12,
        font_obj=None,
    ):
        self.text = text
        self.command = command
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.bg = bg
        self.padx = padx
        self.pady = pady
        self.radius = radius
        self.font_obj = font_obj or font.Font(family="微软雅黑", size=11, weight="bold")
        width = self.font_obj.measure(text) + sx(padx * 2)
        height = self.font_obj.metrics("linespace") + sx(pady * 2)
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.width = width
        self.height = height
        self.current_color = color
        self.draw()
        self.bind("<Enter>", lambda _event: self.set_color(self.hover_color))
        self.bind("<Leave>", lambda _event: self.set_color(self.color))
        self.bind("<Button-1>", lambda _event: self.command())

    def draw(self):
        self.delete("all")
        rounded_rect(
            self,
            sx(1),
            sx(1),
            self.width - sx(1),
            self.height - sx(1),
            sx(self.radius),
            fill=self.current_color,
            outline=self.current_color,
        )
        self.create_text(
            self.width // 2,
            self.height // 2,
            text=self.text,
            fill=self.text_color,
            font=self.font_obj,
        )

    def set_color(self, color):
        self.current_color = color
        self.draw()

    def set_style(self, color, hover_color=None, text_color=None):
        self.color = color
        self.hover_color = hover_color or color
        if text_color is not None:
            self.text_color = text_color
        self.current_color = self.color
        self.draw()

    def set_text(self, text):
        self.text = text
        width = self.font_obj.measure(text) + sx(self.padx * 2)
        self.width = max(self.width, width)
        self.configure(width=self.width)
        self.draw()

    def get_text(self):
        return self.text


class AddTypeDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("新增专业")
        self.geometry(f"{sx(420)}x{sx(210)}")
        self.resizable(False, False)
        self.configure(bg=PANEL_BG)
        self.result = None

        self.transient(parent)
        self.grab_set()
        self.geometry("+%d+%d" % (parent.winfo_rootx() + sx(100), parent.winfo_rooty() + sx(150)))

        frame = ttk.Frame(self, padding=sp((24, 24, 24, 22)), style="Panel.TFrame")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="专业简称").grid(row=0, column=0, sticky="w", pady=sp((0, 12)))
        self.entry_abbr = ttk.Entry(frame, width=18)
        self.entry_abbr.grid(row=0, column=1, sticky="ew", pady=sp((0, 12)), padx=sp((14, 0)))

        ttk.Label(frame, text="专业名称").grid(row=1, column=0, sticky="w", pady=sp((0, 16)))
        self.entry_full = ttk.Entry(frame, width=18)
        self.entry_full.grid(row=1, column=1, sticky="ew", pady=sp((0, 16)), padx=sp((14, 0)))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="e")
        RoundedButton(
            btn_frame,
            text="取消",
            command=self.destroy,
            color=CARD,
            hover_color=FIELD,
            text_color=TEXT_FG,
            bg=PANEL_BG,
            radius=12,
        ).pack(side="left", padx=sp((0, 8)))
        RoundedButton(
            btn_frame,
            text="添加",
            command=self.on_ok,
            color=PRIMARY,
            hover_color=PRIMARY_DARK,
            bg=PANEL_BG,
            radius=12,
        ).pack(side="left")

        self.entry_abbr.focus_set()
        self.bind("<Return>", lambda _event: self.on_ok())
        self.bind("<Escape>", lambda _event: self.destroy())

    def on_ok(self):
        abbr = self.entry_abbr.get().strip().lower()
        full = self.entry_full.get().strip()
        if not abbr or not full:
            messagebox.showwarning("提示", "专业简称和专业名称不能为空", parent=self)
            return
        if not re.fullmatch(r"[a-z0-9_-]+", abbr):
            messagebox.showwarning("提示", "专业简称只能包含英文、数字、下划线或短横线", parent=self)
            self.entry_abbr.focus_set()
            return

        self.result = f"{abbr} - {full}"
        self.destroy()


class CalibreHelper:
    def __init__(self, root):
        global UI_SCALE

        self.root = root
        self.root.title("Epub工具箱 V1.0")
        win_w, win_h, UI_SCALE = scaled_window_size(self.root, page="large", max_screen_ratio=0.9)
        pos_x = max(0, (self.root.winfo_screenwidth() - win_w) // 2)
        pos_y = max(0, (self.root.winfo_screenheight() - win_h) // 2)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(sx(960), sx(640))
        self.root.configure(bg=APP_BG)

        self.font_ui = ("微软雅黑", 12)
        self.font_ui_bold = ("微软雅黑", 12, "bold")
        self.font_small = ("微软雅黑", 11)
        self.font_small_bold = ("微软雅黑", 11, "bold")
        self.font_section = ("微软雅黑", 13, "bold")
        self.font_title = ("微软雅黑", 17, "bold")
        self.label_font = self.font_section
        self.content_font = self.font_ui
        self.button_font = font.Font(family="微软雅黑", size=11, weight="bold")
        self.code_font = font.Font(family="Consolas", size=11)

        self.app_dir = app_base_dir()
        self.config_file = os.path.join(self.app_dir, "tiku_config.json")
        self.types = []
        self.next_nums = {}
        self.current_page = None
        self.pages = {}
        self.view_var = tk.StringVar(value="tts")
        self.nav_buttons = {}
        self.image_epub_app = None
        self.tts_app = None
        self.setup_styles()
        self.load_config()
        self.setup_ui()

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", font=self.font_ui, background=APP_BG, foreground=TEXT_FG)
        style.configure("Toolbar.TFrame", background=APP_BG)
        style.configure("Bar.TFrame", background=BAR)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("PanelBorder.TFrame", background=PANEL_BG, relief="solid", borderwidth=1)
        style.configure("Title.TLabel", background=APP_BG, foreground=TEXT_FG, font=self.font_title)
        style.configure("Subtle.TLabel", background=APP_BG, foreground=MUTED_FG, font=self.font_small)
        style.configure("PanelTitle.TLabel", background=PANEL_BG, foreground=TEXT_FG, font=self.label_font)
        style.configure("Hint.TLabel", background=PANEL_BG, foreground=MUTED_FG, font=self.font_small)
        style.configure("BarLabel.TLabel", background=BAR, foreground=MUTED_FG, font=self.font_small_bold)
        style.configure("TCombobox", padding=sx(6), fieldbackground=FIELD, background=FIELD, foreground=TEXT_FG)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", FIELD)],
            selectbackground=[("readonly", SELECTED)],
            selectforeground=[("readonly", TEXT_FG)],
        )
        style.configure("TEntry", padding=sx(6), fieldbackground=FIELD, foreground=TEXT_FG)

        style.configure("Primary.TButton", background=PRIMARY, foreground=BUTTON_TEXT, borderwidth=0, padding=sp((16, 8)))
        style.map("Primary.TButton", background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_DARK)])
        style.configure("Ghost.TButton", background=CARD, foreground=TEXT_FG, borderwidth=0, padding=sp((14, 8)))
        style.map("Ghost.TButton", background=[("active", FIELD), ("pressed", FIELD)])

    def load_config(self):
        default_types = ["tl - 脱硫", "tj - 热工", "dq - 电气", "gl - 锅炉", "qj - 汽机"]
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "types" in data:
                        self.types = data["types"]
                        self.next_nums = data.get("next_nums", {})
                    else:
                        self.types = default_types
            except Exception:
                self.types = default_types
        else:
            self.types = default_types

    def save_config(self):
        data = {"types": self.types, "next_nums": self.next_nums}
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def setup_ui(self):
        app_shell = ttk.Frame(self.root, style="Toolbar.TFrame")
        app_shell.pack(fill="both", expand=True)
        app_shell.columnconfigure(0, weight=1)
        app_shell.rowconfigure(1, weight=1)

        self.build_navbar(app_shell)

        self.container = ttk.Frame(app_shell, style="Toolbar.TFrame")
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        self.code_page = ttk.Frame(self.container, padding=sp((20, 18, 20, 14)), style="Toolbar.TFrame")
        self.code_page.columnconfigure(0, weight=1)
        self.code_page.rowconfigure(1, weight=1)
        self.pages["code"] = self.code_page

        self.build_toolbar(self.code_page)
        self.build_workspace(self.code_page)

        self.image_page = tk.Frame(self.container, bg=APP_BG)
        self.image_page.columnconfigure(0, weight=1)
        self.image_page.rowconfigure(0, weight=1)
        self.pages["image"] = self.image_page
        self.image_epub_app = ImageToEpubApp(self.image_page, embedded=True)

        self.tts_page = tk.Frame(self.container, bg=APP_BG)
        self.tts_page.columnconfigure(0, weight=1)
        self.tts_page.rowconfigure(0, weight=1)
        self.pages["tts"] = self.tts_page
        self.tts_app = EpubTtsToolApp(self.tts_page)

        self.refresh_type_menu()
        self.show_page("tts")

    def build_navbar(self, parent):
        navbar = tk.Frame(parent, bg=BAR, highlightthickness=sx(1), highlightbackground=LINE)
        navbar.grid(row=0, column=0, sticky="ew")

        inner = tk.Frame(navbar, bg=BAR)
        inner.pack(side="left", padx=sx(18), pady=sp((8, 8)))

        self.nav_buttons["tts"] = self.create_nav_button(inner, "语音导出", "tts")
        self.nav_buttons["tts"].pack(side="left", padx=sp((0, 8)))
        self.nav_buttons["code"] = self.create_nav_button(inner, "片段生成", "code")
        self.nav_buttons["code"].pack(side="left", padx=sp((0, 8)))
        self.nav_buttons["image"] = self.create_nav_button(inner, "图片制书", "image")
        self.nav_buttons["image"].pack(side="left")

    def create_nav_button(self, parent, text, page):
        return RoundedButton(
            parent,
            text=text,
            command=lambda: self.show_page(page),
            color=FIELD,
            hover_color=CARD,
            text_color=TEXT_FG,
            bg=BAR,
            padx=18,
            pady=7,
            radius=12,
            font_obj=font.Font(family="微软雅黑", size=11, weight="bold"),
        )

    def refresh_navbar(self):
        for page, button in self.nav_buttons.items():
            if page == self.current_page:
                button.set_style(PRIMARY, PRIMARY_DARK, BUTTON_TEXT)
            else:
                button.set_style(FIELD, CARD, TEXT_FG)

    def show_page(self, page):
        if self.current_page is not None:
            self.pages[self.current_page].grid_forget()

        self.current_page = page
        self.view_var.set(page)
        self.pages[page].grid(row=0, column=0, sticky="nsew")
        self.refresh_navbar()

        self.root.title("Epub工具箱 V1.0")

    def build_toolbar(self, parent):
        toolbar = tk.Frame(parent, bg=BAR, highlightthickness=sx(1), highlightbackground=LINE)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, sx(14)))
        toolbar.columnconfigure(1, weight=1)

        filter_group = tk.Frame(toolbar, bg=BAR)
        filter_group.grid(row=0, column=0, sticky="w", padx=sx(14), pady=sp((10, 10)))

        action_group = tk.Frame(toolbar, bg=BAR)
        action_group.grid(row=0, column=1, sticky="e", padx=sx(14), pady=sp((10, 10)))

        ttk.Label(filter_group, text="所属专业", style="BarLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(filter_group, textvariable=self.type_var, state="readonly", width=16)
        self.type_combo.grid(row=0, column=1, sticky="w", padx=sp((8, 18)))
        self.type_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_num_display(self.type_var.get()))

        ttk.Label(filter_group, text="当前题号", style="BarLabel.TLabel").grid(row=0, column=2, sticky="w")
        self.entry_num = ttk.Entry(filter_group, width=6, justify="center")
        self.entry_num.grid(row=0, column=3, sticky="w", padx=sp((8, 0)))

        self.make_button(action_group, "新增专业", self.add_new_type, color=BROWN, hover=BROWN_DARK).pack(side="left", padx=sp((0, 8)))
        self.make_button(action_group, "生成片段", self.generate_code, color=GREEN, hover=GREEN_DARK).pack(side="left", padx=sp((0, 8)))
        self.btn_copy = self.make_button(action_group, "复制片段", self.copy_to_clipboard, color=BLUE, hover=BLUE_DARK)
        self.btn_copy.pack(side="left", padx=sp((0, 8)))
        self.make_button(action_group, "清空", self.clear_input, color=RED, hover="#864f49").pack(side="left")

    def make_button(self, parent, text, command, color=GREEN, hover=GREEN_DARK):
        return RoundedButton(
            parent,
            text=text,
            command=command,
            color=color,
            hover_color=hover,
            bg=BAR,
            font_obj=self.button_font,
        )

    def build_workspace(self, parent):
        workspace = ttk.Frame(parent, style="Toolbar.TFrame")
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=11, uniform="main")
        workspace.columnconfigure(1, weight=13, uniform="main")
        workspace.rowconfigure(0, weight=1)

        input_panel = self.create_panel(workspace)
        input_panel.grid(row=0, column=0, sticky="nsew", padx=sp((0, 8)))
        input_panel.rowconfigure(2, weight=1)
        input_panel.columnconfigure(0, weight=1)

        ttk.Label(input_panel, text="题目内容", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(input_panel, text="不需要输入题号，生成时会自动补上当前题号", style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", pady=sp((4, 8))
        )
        self.text_title = self.create_text_box(input_panel, height=6, bg=FIELD, fg=TEXT_FG)
        self.text_title.grid(row=2, column=0, sticky="nsew", pady=sp((0, 14)))

        ttk.Label(input_panel, text="答案内容", style="PanelTitle.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Label(input_panel, text="每一行会生成一个独立段落", style="Hint.TLabel").grid(
            row=4, column=0, sticky="w", pady=sp((4, 8))
        )
        self.text_answer = self.create_text_box(input_panel, height=16, bg=FIELD, fg=TEXT_FG)
        self.text_answer.grid(row=5, column=0, sticky="nsew")
        input_panel.rowconfigure(5, weight=3)

        output_panel = self.create_panel(workspace)
        output_panel.grid(row=0, column=1, sticky="nsew", padx=sp((8, 0)))
        output_panel.rowconfigure(2, weight=1)
        output_panel.columnconfigure(0, weight=1)

        ttk.Label(output_panel, text="EPUB HTML 片段", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(output_panel, text="复制后粘贴到 EPUB 编辑器的正文区域", style="Hint.TLabel").grid(
            row=1, column=0, sticky="w", pady=sp((4, 8))
        )
        self.text_output = self.create_text_box(output_panel, height=24, bg=CODE_BG, fg=CODE_FG, font_obj=self.code_font)
        self.text_output.grid(row=2, column=0, sticky="nsew")

    def create_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=PANEL_BG,
            padx=sx(16),
            pady=sx(14),
            highlightthickness=sx(1),
            highlightbackground=LINE,
        )
        return panel

    def create_text_box(self, parent, height, bg, fg, font_obj=None):
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            undo=True,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PRIMARY,
            padx=sx(12),
            pady=sx(10),
            bg=bg,
            fg=fg,
            insertbackground=fg,
            selectbackground=SELECTED,
            selectforeground=TEXT_FG,
            font=font_obj or self.content_font,
        )
        self.bind_mousewheel(text)
        return text

    def bind_mousewheel(self, widget):
        def on_mousewheel(event):
            if event.delta:
                widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        def on_scroll_up(_event):
            widget.yview_scroll(-1, "units")
            return "break"

        def on_scroll_down(_event):
            widget.yview_scroll(1, "units")
            return "break"

        widget.bind("<MouseWheel>", on_mousewheel)
        widget.bind("<Button-4>", on_scroll_up)
        widget.bind("<Button-5>", on_scroll_down)

    def refresh_type_menu(self):
        self.type_combo["values"] = self.types
        if self.types:
            self.type_combo.current(0)
            self.update_num_display(self.types[0])

    def add_new_type(self):
        dialog = AddTypeDialog(self.root)
        self.root.wait_window(dialog)
        if not dialog.result:
            return

        new_abbr = dialog.result.split(" - ")[0]
        existing_abbrs = {item.split(" - ")[0] for item in self.types}
        if new_abbr in existing_abbrs:
            messagebox.showwarning("提示", f"专业简称 {new_abbr} 已存在，请换一个。")
            return

        self.types.append(dialog.result)
        self.save_config()
        self.refresh_type_menu()
        self.type_var.set(dialog.result)
        self.update_num_display(dialog.result)

    def update_num_display(self, selected_type):
        if not selected_type:
            return
        q_type = selected_type.split(" - ")[0]
        next_num = self.next_nums.get(q_type, 1)
        self.entry_num.delete(0, tk.END)
        self.entry_num.insert(0, str(next_num))

    def generate_code(self):
        current_selection = self.type_var.get()
        if not current_selection:
            return

        q_type = current_selection.split(" - ")[0]
        raw_title = self.text_title.get("1.0", tk.END).strip()
        raw_answer = self.text_answer.get("1.0", tk.END).strip()

        try:
            q_num = int(self.entry_num.get())
        except ValueError:
            messagebox.showerror("错误", "题号必须是数字！")
            return
        if q_num < 1:
            messagebox.showerror("错误", "题号必须大于 0！")
            return

        if not raw_title or not raw_answer:
            messagebox.showwarning("提示", "题目和答案内容不能为空。")
            return

        safe_title = html.escape(raw_title)
        res_id = f"{q_type}_q{q_num}"
        ans_p = ""
        for line in raw_answer.split("\n"):
            line = line.strip()
            if line:
                safe_line = html.escape(line)
                ans_p += f"        <p>{safe_line}</p>\n"

        code = f'<h2 id="{res_id}">{q_num}. {safe_title}</h2>\n<div class="answer-box">\n    <p><b>答：</b></p>\n{ans_p}</div>\n'
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert(tk.END, code)
        self.next_nums[q_type] = q_num + 1
        self.save_config()
        self.update_num_display(current_selection)

    def copy_to_clipboard(self):
        content = self.text_output.get("1.0", tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)

            original_text = self.btn_copy.get_text()
            self.btn_copy.set_text("已复制")

            def restore_and_prepare():
                self.btn_copy.set_text(original_text)
                self.clear_input()
                self.text_title.focus_set()

            self.root.after(800, restore_and_prepare)

    def clear_input(self):
        self.text_title.delete("1.0", tk.END)
        self.text_answer.delete("1.0", tk.END)
        self.text_output.delete("1.0", tk.END)


if __name__ == "__main__":
    enable_dpi_awareness()
    root = create_root()
    app = CalibreHelper(root)
    root.mainloop()
