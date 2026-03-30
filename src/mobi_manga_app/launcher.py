from __future__ import annotations

import ctypes
import json
import socket
import sys
import threading
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .api import create_handler


APP_NAME = "文乃"
PRODUCT_NAME = "漫画画质提升"
FIXED_PORT = 47464


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "runtime"
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return runtime_root() / ".launcher" / "config.json"


def log_file_path() -> Path:
    return runtime_root() / ".launcher" / "launcher.log"


def icon_path() -> Path:
    root = bundle_root()
    for candidate in (root / "app.ico", root / "image.png"):
        if candidate.exists():
            return candidate
    return root


def default_source_root() -> Path:
    return runtime_root() / "sources"


def default_output_root() -> Path:
    return runtime_root() / "outputs"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@dataclass(slots=True)
class ModelEntry:
    name: str
    kind: str
    status: str
    note: str = ""


@dataclass(slots=True)
class LauncherConfig:
    source_root: str
    output_root: str
    auto_start_service: bool = False
    theme_mode: str = "dark"
    models: list[ModelEntry] = field(default_factory=list)


class LocalServer:
    def __init__(self, runtime_dir: Path, static_dir: Path, source_root: Path, output_root: Path) -> None:
        self.runtime_dir = runtime_dir
        self.static_dir = static_dir
        self.source_root = source_root
        self.output_root = output_root
        self.port = FIXED_PORT
        self.server = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        if self.server is not None:
            return
        if port_in_use(self.port):
            raise OSError(f"端口 {self.port} 已被占用。")
        if not self.static_dir.exists():
            raise FileNotFoundError(f"前端构建目录不存在: {self.static_dir}")

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.source_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

        handler = create_handler(
            repo_root=self.runtime_dir,
            source_root=self.source_root,
            static_root=self.static_dir,
            default_output_root=self.output_root,
        )

        from http.server import ThreadingHTTPServer

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self.thread = None


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 24, 24, 24)
        self.body.setSpacing(14)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("CardTitle")
            self.body.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("CardSubtitle")
            subtitle_label.setWordWrap(True)
            self.body.addWidget(subtitle_label)


class NavButton(QToolButton):
    def __init__(self, label: str, glyph: str) -> None:
        super().__init__()
        self.setText(f"{glyph}\n{label}")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(QSize(64, 72))
        self.setMaximumWidth(80)
        self.setObjectName("NavButton")


class LauncherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.bundle_dir = bundle_root()
        self.runtime_dir = runtime_root()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir = self.bundle_dir / "frontend" / "dist"
        self.server: LocalServer | None = None
        self.log_lines: list[str] = []
        self.log_file = log_file_path()
        self.config = self.load_config()
        self.theme_mode = self.config.theme_mode if self.config.theme_mode in {"dark", "light"} else "dark"
        self.nav_buttons: list[NavButton] = []

        app_icon = QIcon(str(icon_path()))
        self.setWindowIcon(app_icon)
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 880)
        self.setMinimumSize(1200, 750)
        self.build_ui()
        self.apply_theme()
        self.refresh_status()
        self.log("启动器已加载，等待启动服务。")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)

        if self.config.auto_start_service:
            QTimer.singleShot(250, self.start_service)

    def load_config(self) -> LauncherConfig:
        models = [
            ModelEntry("内置拆页与增强", "主流程", "已接入", "支持 mobi、pdf、cbz、zip 和图片目录。"),
            ModelEntry("多文件合并封装", "封装模块", "已接入", "可将多个选中素材顺序拆页后合并导出。"),
            ModelEntry("waifu2x / Real-ESRGAN", "模型扩展", "预留", "后续可替换为更高质量增强引擎。"),
        ]
        path = config_path()
        source_root = default_source_root()
        output_root = default_output_root()
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                stored_models = [ModelEntry(**item) for item in payload.get("models", [])]
                return LauncherConfig(
                    source_root=payload.get("source_root") or str(source_root),
                    output_root=payload.get("output_root") or str(output_root),
                    auto_start_service=bool(payload.get("auto_start_service", False)),
                    theme_mode=payload.get("theme_mode") or "dark",
                    models=stored_models or models,
                )
            except Exception:
                pass
        return LauncherConfig(str(source_root), str(output_root), False, "dark", models)

    def save_config(self) -> None:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_root": self.source_edit.text().strip(),
            "output_root": self.output_edit.text().strip(),
            "auto_start_service": self.auto_start_check.isChecked(),
            "theme_mode": self.theme_mode,
            "models": [asdict(item) for item in self.config.models],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(8)

        brand_card = QFrame()
        brand_card.setObjectName("BrandCard")
        brand_layout = QVBoxLayout(brand_card)
        brand_layout.setContentsMargins(10, 12, 10, 12)
        brand_layout.setSpacing(6)
        brand_mark = QLabel("文")
        brand_mark.setObjectName("BrandMark")
        brand_layout.addWidget(brand_mark, 0, Qt.AlignHCenter)
        brand_title = QLabel("文乃")
        brand_title.setObjectName("BrandTitle")
        brand_title.setAlignment(Qt.AlignHCenter)
        brand_subtitle = QLabel(PRODUCT_NAME)
        brand_subtitle.setObjectName("BrandSubtitle")
        brand_subtitle.setAlignment(Qt.AlignHCenter)
        brand_subtitle.setWordWrap(True)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)
        sidebar_layout.addWidget(brand_card)

        nav_specs = [
            ("启动", "▶"),
            ("目录", "▣"),
            ("模型", "◇"),
            ("日志", "≡"),
            ("设置", "⚙"),
        ]
        nav_wrap = QVBoxLayout()
        nav_wrap.setSpacing(12)
        for index, (label, glyph) in enumerate(nav_specs):
            button = NavButton(label, glyph)
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_buttons.append(button)
            nav_wrap.addWidget(button)
        sidebar_layout.addLayout(nav_wrap)
        sidebar_layout.addStretch(1)
        brand_layout.addWidget(brand_subtitle)
        sidebar_layout.addWidget(brand_card)

        nav_specs = [
            ("启动", "▶"),
            ("目录", "▣"),
            ("模型", "◇"),
            ("日志", "≡"),
            ("设置", "⚙"),
        ]
        nav_wrap = QVBoxLayout()
        nav_wrap.setSpacing(10)
        for index, (label, glyph) in enumerate(nav_specs):
            button = NavButton(label, glyph)
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_buttons.append(button)
            nav_wrap.addWidget(button)
        sidebar_layout.addLayout(nav_wrap)
        sidebar_layout.addStretch(1)
        self.theme_button = QPushButton("浅色" if self.theme_mode == "dark" else "深色")
        self.theme_button.setObjectName("ThemeButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.theme_button)
        shell.addWidget(sidebar, 0)

        workspace = QVBoxLayout()
        workspace.setContentsMargins(24, 24, 24, 24)
        workspace.setSpacing(20)
        shell.addLayout(workspace, 1)

        hero = Card()
        hero.setObjectName("HeroCard")
        hero_top = QHBoxLayout()
        hero_top.setSpacing(16)

        hero_badge = QLabel("文乃")
        hero_badge.setObjectName("HeroBadge")
        hero_top.addWidget(hero_badge, 0)
        hero_top.addStretch(1)
        self.state_badge = QLabel("未启动")
        self.state_badge.setObjectName("StateBadge")
        hero_top.addWidget(self.state_badge, 0)
        hero.body.addLayout(hero_top)

        hero_title = QLabel(PRODUCT_NAME)
        hero_title.setObjectName("HeroTitle")
        hero.body.addWidget(hero_title)

        hero_subtitle = QLabel("桌面启动器负责目录、服务、主题和日志。真正的导入、拆页、增强、封装都在网页工作台中完成。")
        hero_subtitle.setObjectName("HeroSubtitle")
        hero_subtitle.setWordWrap(True)
        hero.body.addWidget(hero_subtitle)
        workspace.addWidget(hero)

        self.pages = QStackedWidget()
        workspace.addWidget(self.pages, 1)

        home_page = QWidget()
        home_layout = QGridLayout(home_page)
        home_layout.setHorizontalSpacing(12)
        home_layout.setVerticalSpacing(12)

        control_card = Card("启动服务", "先设置素材和输出目录。服务启动后可在浏览器中打开工作台。")
        control_form = QVBoxLayout()
        control_form.setSpacing(16)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("素材目录"))
        self.source_edit = QLineEdit(self.config.source_root)
        source_row.addWidget(self.source_edit, 1)
        pick_source = QPushButton("选择")
        pick_source.clicked.connect(self.pick_source_dir)
        source_row.addWidget(pick_source)
        control_form.addLayout(source_row)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录"))
        self.output_edit = QLineEdit(self.config.output_root)
        output_row.addWidget(self.output_edit, 1)
        pick_output = QPushButton("选择")
        pick_output.clicked.connect(self.pick_output_dir)
        output_row.addWidget(pick_output)
        control_form.addLayout(output_row)

        self.auto_start_check = QCheckBox("启动器打开后自动启动服务")
        self.auto_start_check.setChecked(self.config.auto_start_service)
        self.auto_start_check.toggled.connect(lambda _: self.save_config())
        control_form.addWidget(self.auto_start_check)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("启动服务")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_service)
        button_row.addWidget(self.start_button)
        self.stop_button = QPushButton("停止服务")
        self.stop_button.clicked.connect(self.stop_service)
        button_row.addWidget(self.stop_button)
        browser_button = QPushButton("打开浏览器")
        browser_button.setObjectName("AccentButton")
        browser_button.clicked.connect(self.open_browser)
        button_row.addWidget(browser_button)
        control_form.addLayout(button_row)

        links_row = QHBoxLayout()
        open_source = QPushButton("打开素材目录")
        open_source.clicked.connect(lambda: self.open_dir(Path(self.source_edit.text().strip())))
        links_row.addWidget(open_source)
        open_output = QPushButton("打开输出目录")
        open_output.clicked.connect(lambda: self.open_dir(Path(self.output_edit.text().strip())))
        links_row.addWidget(open_output)
        open_log = QPushButton("打开日志")
        open_log.clicked.connect(lambda: self.open_dir(self.log_file))
        links_row.addWidget(open_log)
        control_form.addLayout(links_row)

        quick_title = QLabel("常用入口")
        quick_title.setObjectName("SectionLabel")
        control_form.addWidget(quick_title)
        quick_info = QLabel("浏览器工作台负责导入、单步执行、增强、封装和合并。启动器负责目录、服务和日志控制。")
        quick_info.setObjectName("BodyText")
        quick_info.setWordWrap(True)
        control_form.addWidget(quick_info)

        control_card.body.addLayout(control_form)
        home_layout.addWidget(control_card, 0, 0)

        status_card = Card("控制台", "右侧保留日志预览和运行状态。")
        self.status_text = QLabel("服务尚未启动。")
        self.status_text.setObjectName("StatusText")
        self.status_text.setWordWrap(True)
        status_card.body.addWidget(self.status_text)

        self.summary_box = QLabel("浏览器地址: -")
        self.summary_box.setObjectName("SummaryBox")
        self.summary_box.setWordWrap(True)
        status_card.body.addWidget(self.summary_box)

        self.log_preview = QPlainTextEdit()
        self.log_preview.setReadOnly(True)
        self.log_preview.setObjectName("LogBox")
        self.log_preview.setMinimumHeight(160)
        status_card.body.addWidget(self.log_preview)
        home_layout.addWidget(status_card, 0, 1)

        model_card = Card("模型", "当前以稳定主流程为先，模型扩展位先保留。")
        for item in self.config.models:
            mini = QFrame()
            mini.setObjectName("MiniCard")
            mini_layout = QVBoxLayout(mini)
            mini_layout.setContentsMargins(18, 18, 18, 18)
            mini_layout.setSpacing(8)
            title = QLabel(item.name)
            title.setObjectName("MiniTitle")
            meta = QLabel(f"{item.kind} | {item.status}")
            meta.setObjectName("MiniMeta")
            note = QLabel(item.note)
            note.setObjectName("MiniNote")
            note.setWordWrap(True)
            mini_layout.addWidget(title)
            mini_layout.addWidget(meta)
            mini_layout.addWidget(note)
            model_card.body.addWidget(mini)
        home_layout.addWidget(model_card, 1, 0)

        logs_card = Card("日志", "这里显示完整启动器日志。网页任务日志会在浏览器工作台里展示。")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("LogBox")
        self.log_view.setMinimumHeight(180)
        logs_card.body.addWidget(self.log_view)
        clear_button = QPushButton("清空日志")
        clear_button.clicked.connect(self.clear_logs)
        logs_card.body.addWidget(clear_button)
        home_layout.addWidget(logs_card, 1, 1)

        paths_page = QWidget()
        paths_layout = QVBoxLayout(paths_page)
        paths_layout.setSpacing(16)
        path_summary = Card("目录与输出", "这里单独管理素材目录、输出目录以及网页工作台入口。")
        path_content = QVBoxLayout()
        path_content.setSpacing(16)
        path_content.addWidget(QLabel("素材目录"))
        self.paths_source_edit = QLineEdit(self.config.source_root)
        self.paths_source_edit.textChanged.connect(self.source_edit.setText)
        self.source_edit.textChanged.connect(self.paths_source_edit.setText)
        path_content.addWidget(self.paths_source_edit)
        pick_source_large = QPushButton("选择素材目录")
        pick_source_large.clicked.connect(self.pick_source_dir)
        path_content.addWidget(pick_source_large)
        path_content.addWidget(QLabel("输出目录"))
        self.paths_output_edit = QLineEdit(self.config.output_root)
        self.paths_output_edit.textChanged.connect(self.output_edit.setText)
        self.output_edit.textChanged.connect(self.paths_output_edit.setText)
        path_content.addWidget(self.paths_output_edit)
        pick_output_large = QPushButton("选择输出目录")
        pick_output_large.clicked.connect(self.pick_output_dir)
        path_content.addWidget(pick_output_large)
        path_links = QHBoxLayout()
        open_source_large = QPushButton("打开素材目录")
        open_source_large.clicked.connect(lambda: self.open_dir(Path(self.source_edit.text().strip())))
        path_links.addWidget(open_source_large)
        open_output_large = QPushButton("打开输出目录")
        open_output_large.clicked.connect(lambda: self.open_dir(Path(self.output_edit.text().strip())))
        path_links.addWidget(open_output_large)
        open_browser_large = QPushButton("打开网页工作台")
        open_browser_large.setObjectName("AccentButton")
        open_browser_large.clicked.connect(self.open_browser)
        path_links.addWidget(open_browser_large)
        path_content.addLayout(path_links)
        path_summary.body.addLayout(path_content)
        paths_layout.addWidget(path_summary)
        paths_layout.addStretch(1)

        models_page = QWidget()
        models_layout = QVBoxLayout(models_page)
        models_layout.setSpacing(12)
        models_intro = Card("模型状态", "这里展示当前增强能力和后续预留位。")
        for item in self.config.models:
            mini = QFrame()
            mini.setObjectName("MiniCard")
            mini_layout = QVBoxLayout(mini)
            mini_layout.setContentsMargins(16, 16, 16, 16)
            mini_layout.setSpacing(6)
            title = QLabel(item.name)
            title.setObjectName("MiniTitle")
            meta = QLabel(f"{item.kind} | {item.status}")
            meta.setObjectName("MiniMeta")
            mini_layout.addWidget(title)
            mini_layout.addWidget(meta)
            note = QLabel(item.note)
            note.setWordWrap(True)
            note.setObjectName("MiniNote")
            mini_layout.addWidget(note)
            models_intro.body.addWidget(mini)
        models_layout.addWidget(models_intro)
        models_layout.addStretch(1)

        logs_page = QWidget()
        logs_layout = QVBoxLayout(logs_page)
        logs_layout.setSpacing(12)
        logs_panel = Card("完整日志", "这里保留启动器全量日志，错误不会再只显示一句失败。")
        self.full_log_view = QPlainTextEdit()
        self.full_log_view.setReadOnly(True)
        self.full_log_view.setObjectName("LogBox")
        self.full_log_view.setMinimumHeight(320)
        logs_panel.body.addWidget(self.full_log_view)
        logs_layout.addWidget(logs_panel)

        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setSpacing(12)
        settings_card = Card("设置", "主题、自动启动和窗口行为都集中在这里。")
        settings_body = QVBoxLayout()
        settings_body.setSpacing(12)
        theme_row = QHBoxLayout()
        theme_label = QLabel("当前主题")
        self.theme_text = QLabel("")
        self.theme_text.setObjectName("SummaryBox")
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_text, 1)
        settings_body.addLayout(theme_row)
        self.settings_auto_start = QCheckBox("启动器打开后自动启动服务")
        self.settings_auto_start.setChecked(self.config.auto_start_service)
        self.settings_auto_start.toggled.connect(self.sync_auto_start)
        settings_body.addWidget(self.settings_auto_start)
        settings_hint = QLabel("浅色主题会尽量接近网页端色调，深色主题维持桌面控制台风格。")
        settings_hint.setObjectName("BodyText")
        settings_hint.setWordWrap(True)
        settings_body.addWidget(settings_hint)
        theme_toggle = QPushButton("切换明暗主题")
        theme_toggle.clicked.connect(self.toggle_theme)
        settings_body.addWidget(theme_toggle)
        settings_card.body.addLayout(settings_body)
        settings_layout.addWidget(settings_card)
        settings_layout.addStretch(1)

        self.pages.addWidget(home_page)
        self.pages.addWidget(paths_page)
        self.pages.addWidget(models_page)
        self.pages.addWidget(logs_page)
        self.pages.addWidget(settings_page)
        self.switch_page(0)

    def apply_theme(self) -> None:
        if self.theme_mode == "light":
            stylesheet = """
            QWidget { background: #edf8f6; color: #12363a; font-size: 14px; font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif; }
            QMainWindow { background: #e6f5f2; }
            QLabel { background: transparent; border: 0; }
            QFrame#Sidebar { background: rgba(255,255,255,0.78); border: 1px solid #c7e4df; border-radius: 26px; min-width: 110px; max-width: 110px; }
            QFrame#BrandCard { background: transparent; border: 0; }
            QLabel#BrandMark { min-width: 52px; min-height: 52px; max-width: 52px; max-height: 52px; border-radius: 18px; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #17b6ad, stop:1 #28c66f); color: white; font: 800 22px "Segoe UI"; qproperty-alignment: AlignCenter; }
            QLabel#BrandTitle { color: #174048; font: 700 16px "Microsoft YaHei UI"; margin-top: 4px; }
            QLabel#BrandSubtitle { color: #5b7d82; font-size: 13px; margin-top: 2px; }
            QToolButton#NavButton { background: rgba(255,255,255,0.72); border: 1px solid #d7efeb; border-radius: 20px; padding: 14px 8px; color: #2b5255; font: 700 13px "Microsoft YaHei UI"; min-height: 24px; }
            QToolButton#NavButton:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #dff7f3, stop:1 #effaf7); border: 1px solid #7ed2c8; color: #0d6763; }
            QPushButton#ThemeButton { background: #ffffff; border: 1px solid #d6ebe6; border-radius: 18px; padding: 14px 12px; color: #1c5456; font: 700 13px "Microsoft YaHei UI"; }
            QFrame#Card, QFrame#HeroCard { background: rgba(255,255,255,0.85); border: 1px solid #d3ebe5; border-radius: 24px; padding: 20px; }
            QFrame#HeroCard { min-height: 180px; padding: 24px; }
            QLabel#CardTitle { color: #163d45; font: 700 22px "Microsoft YaHei UI"; margin-bottom: 8px; }
            QLabel#CardSubtitle, QLabel#BodyText, QLabel#MiniMeta { color: #67858a; line-height: 1.6; }
            QLabel#HeroBadge { color: #0d9f99; font: 700 13px "Microsoft YaHei UI"; }
            QLabel#HeroTitle { color: #153842; font: 700 40px "Microsoft YaHei UI"; margin-bottom: 12px; }
            QLabel#HeroSubtitle { color: #5e7b80; font-size: 16px; line-height: 1.5; }
            QLabel#StateBadge { background: #f4fbfa; border: 1px solid #cfe6e1; border-radius: 18px; padding: 12px 18px; color: #127f7a; font: 700 14px "Microsoft YaHei UI"; }
            QLabel#StatusText { color: #244e56; font-size: 15px; margin: 8px 0; }
            QLabel#SummaryBox { background: #f4fbfa; border: 1px solid #d7ece8; border-radius: 18px; padding: 16px 18px; color: #537378; margin: 8px 0; }
            QLabel#SectionLabel { color: #163d45; font: 700 18px "Microsoft YaHei UI"; margin-top: 20px; margin-bottom: 12px; }
            QFrame#MiniCard { background: #f7fcfb; border: 1px solid #d8ece8; border-radius: 20px; padding: 16px; margin: 8px 0; }
            QLabel#MiniTitle { color: #173f47; font: 700 16px "Microsoft YaHei UI"; margin-bottom: 6px; }
            QLabel#MiniNote { color: #58747a; line-height: 1.5; }
            QLineEdit { background: #ffffff; border: 1px solid #d2e7e3; border-radius: 16px; padding: 13px 16px; color: #173b40; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #13b1a9; }
            QCheckBox { color: #33565b; spacing: 10px; padding: 8px 0; }
            QPushButton { background: #ffffff; border: 1px solid #d3e7e2; border-radius: 16px; padding: 13px 18px; color: #24494f; font-size: 14px; min-height: 20px; }
            QPushButton:hover { background: #f5fbfa; }
            QPushButton#PrimaryButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #17b6ad, stop:1 #45c98e); border: 0; color: white; font: 700 15px "Microsoft YaHei UI"; padding: 14px 20px; }
            QPushButton#AccentButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6ee0d5, stop:1 #9cf0b3); border: 0; color: #114447; font: 700 15px "Microsoft YaHei UI"; padding: 14px 20px; }
            QPlainTextEdit#LogBox { background: #fcffff; border: 1px solid #d6ece7; border-radius: 20px; padding: 16px; color: #1e4b52; selection-background-color: #9fe8de; font-size: 13px; line-height: 1.6; }
            """
        else:
            stylesheet = """
            QWidget { background: #1b1d24; color: #eef2ff; font-size: 14px; font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif; }
            QMainWindow { background: #14161c; }
            QLabel { background: transparent; border: 0; }
            QFrame#Sidebar { background: #262a34; border: 0; border-right: 1px solid #1a1d24; min-width: 80px; max-width: 80px; }
            QFrame#BrandCard { background: transparent; border: 0; }
            QLabel#BrandMark { min-width: 52px; min-height: 52px; max-width: 52px; max-height: 52px; border-radius: 18px; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2f80ff, stop:1 #3658d5); color: white; font: 800 22px "Segoe UI"; qproperty-alignment: AlignCenter; }
            QLabel#BrandTitle { color: #f4f7ff; font: 700 16px "Microsoft YaHei UI"; margin-top: 4px; }
            QLabel#BrandSubtitle { color: #96a3c5; font-size: 13px; margin-top: 2px; }
            QToolButton#NavButton { background: transparent; border: 0; border-radius: 12px; padding: 16px 8px; color: #9ca3c0; font: 600 12px "Microsoft YaHei UI"; min-height: 32px; }
            QToolButton#NavButton:checked { background: rgba(78, 124, 255, 0.15); color: #6bb1ff; }
            QPushButton#ThemeButton { background: #2f3443; border: 1px solid #3d465d; border-radius: 18px; padding: 14px 12px; color: #f0f4ff; font: 700 13px "Microsoft YaHei UI"; }
            QFrame#Card, QFrame#HeroCard { background: #252934; border: 1px solid #2d3240; border-radius: 16px; padding: 28px; }
            QFrame#HeroCard { min-height: 200px; padding: 32px; }
            QLabel#CardTitle { color: #ffffff; font: 700 22px "Microsoft YaHei UI"; margin-bottom: 8px; }
            QLabel#CardSubtitle, QLabel#BodyText, QLabel#MiniMeta { color: #9ca7c0; line-height: 1.6; }
            QLabel#HeroBadge { color: #5ba6ff; font: 700 13px "Microsoft YaHei UI"; }
            QLabel#HeroTitle { color: #ffffff; font: 700 40px "Microsoft YaHei UI"; margin-bottom: 12px; }
            QLabel#HeroSubtitle { color: #aab3c9; font-size: 16px; line-height: 1.5; }
            QLabel#StateBadge { background: #2c3140; border: 1px solid #3b4359; border-radius: 18px; padding: 12px 18px; color: #6bb1ff; font: 700 14px "Microsoft YaHei UI"; }
            QLabel#StatusText { color: #dfe6ff; font-size: 15px; margin: 8px 0; }
            QLabel#SummaryBox { background: #1b1f28; border: 1px solid #32384b; border-radius: 18px; padding: 16px 18px; color: #b8c2dc; margin: 8px 0; }
            QLabel#SectionLabel { color: #ffffff; font: 700 18px "Microsoft YaHei UI"; margin-top: 20px; margin-bottom: 12px; }
            QFrame#MiniCard { background: #2a2f3b; border: 1px solid #363d4e; border-radius: 20px; padding: 16px; margin: 8px 0; }
            QLabel#MiniTitle { color: #ffffff; font: 700 16px "Microsoft YaHei UI"; margin-bottom: 6px; }
            QLabel#MiniNote { color: #c6d0ea; line-height: 1.5; }
            QLineEdit { background: #1b1f28; border: 1px solid #363c4f; border-radius: 16px; padding: 13px 16px; color: #f0f4ff; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #4a7cff; }
            QCheckBox { color: #dbe4ff; spacing: 10px; padding: 8px 0; }
            QPushButton { background: #2f3443; border: 1px solid #3d465d; border-radius: 16px; padding: 13px 18px; color: #f0f4ff; font-size: 14px; min-height: 20px; }
            QPushButton:hover { background: #394157; }
            QPushButton#PrimaryButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff7b1a, stop:1 #ff8f2f); border: 0; color: white; font: 700 15px "Microsoft YaHei UI"; padding: 14px 20px; }
            QPushButton#AccentButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3479ff, stop:1 #4c90ff); border: 0; color: white; font: 700 15px "Microsoft YaHei UI"; padding: 14px 20px; }
            QPlainTextEdit#LogBox { background: #15181f; border: 1px solid #31384b; border-radius: 20px; padding: 16px; color: #d9e7ff; selection-background-color: #315ed2; font-size: 13px; line-height: 1.6; }
            """
        self.setStyleSheet(stylesheet)
        if hasattr(self, "theme_button"):
            self.theme_button.setText("浅色" if self.theme_mode == "dark" else "深色")
        if hasattr(self, "theme_text"):
            self.theme_text.setText("深色控制台" if self.theme_mode == "dark" else "浅色工作台")

    def switch_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.apply_theme()
        self.save_config()

    def sync_auto_start(self, checked: bool) -> None:
        self.auto_start_check.setChecked(checked)
        self.save_config()

    def pick_source_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择素材目录", self.source_edit.text().strip() or str(Path.home()))
        if selected:
            self.source_edit.setText(selected)
            self.save_config()
            self.log(f"素材目录已切换: {selected}")

    def pick_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text().strip() or str(Path.home()))
        if selected:
            self.output_edit.setText(selected)
            self.save_config()
            self.log(f"输出目录已切换: {selected}")

    def current_server(self) -> LocalServer:
        return LocalServer(
            runtime_dir=self.runtime_dir,
            static_dir=self.static_dir,
            source_root=Path(self.source_edit.text().strip() or self.config.source_root),
            output_root=Path(self.output_edit.text().strip() or self.config.output_root),
        )

    def start_service(self) -> None:
        self.save_config()
        try:
            if self.server is not None:
                self.log(f"服务已经在运行: {self.server.url}")
                return
            server = self.current_server()
            self.log(
                "开始启动服务",
                extra=[
                    f"runtime_dir={self.runtime_dir}",
                    f"static_dir={self.static_dir}",
                    f"source_dir={self.source_edit.text().strip()}",
                    f"output_dir={self.output_edit.text().strip()}",
                    f"auto_start_service={self.auto_start_check.isChecked()}",
                ],
            )
            server.start()
            self.server = server
            self.log(f"服务已启动: {server.url}")
        except Exception as exc:
            self.log(f"启动失败: {exc}", extra=[traceback.format_exc().strip()])
        finally:
            self.refresh_status()

    def stop_service(self) -> None:
        if self.server is None:
            self.log("当前没有运行中的服务。")
            return
        self.server.stop()
        self.server = None
        self.log("服务已停止。")
        self.refresh_status()

    def open_browser(self) -> None:
        if self.server is None:
            self.log("浏览器未打开: 服务尚未启动。")
            return
        QDesktopServices.openUrl(QUrl(self.server.url))
        self.log(f"已打开浏览器: {self.server.url}")

    def open_dir(self, path: Path) -> None:
        if not path.exists():
            self.log(f"路径不存在: {path}")
            return
        target = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.log(f"已打开路径: {path}")

    def refresh_status(self) -> None:
        running = self.server is not None and self.server.thread is not None and self.server.thread.is_alive()
        self.state_badge.setText("运行中" if running else "未启动")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

        source_root = self.source_edit.text().strip()
        output_root = self.output_edit.text().strip()
        if running and self.server is not None:
            self.status_text.setText(
                f"运行中\n\n浏览器地址: {self.server.url}\n素材目录: {source_root}\n输出目录: {output_root}"
            )
            self.summary_box.setText("浏览器地址: " + self.server.url + "\n启动器已就绪，可继续导入、单步执行、增强、封装与合并。")
        else:
            self.status_text.setText(
                f"服务已停止。\n\n素材目录: {source_root}\n输出目录: {output_root}\n端口: {FIXED_PORT}"
            )
            self.summary_box.setText("浏览器地址: -\n请先启动本地服务。启动器已修复重复弹窗问题。")

    def log(self, message: str, *, extra: list[str] | None = None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entries = [f"[{timestamp}] {message}"]
        if extra:
            entries.extend(f"    {line}" for line in extra if line)
        self.log_lines.extend(entries)
        self.log_lines = self.log_lines[-500:]
        content = "\n".join(self.log_lines)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.write_text(content, encoding="utf-8")
        if hasattr(self, "log_preview"):
            self.log_preview.setPlainText(content)
            self.log_preview.verticalScrollBar().setValue(self.log_preview.verticalScrollBar().maximum())
        if hasattr(self, "log_view"):
            self.log_view.setPlainText(content)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        if hasattr(self, "full_log_view"):
            self.full_log_view.setPlainText(content)
            self.full_log_view.verticalScrollBar().setValue(self.full_log_view.verticalScrollBar().maximum())

    def clear_logs(self) -> None:
        self.log_lines = []
        self.log("日志已清空。")


def main() -> int:
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("manga.enhancer.launcher")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if icon_path().exists():
        app.setWindowIcon(QIcon(str(icon_path())))
    window = LauncherWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
