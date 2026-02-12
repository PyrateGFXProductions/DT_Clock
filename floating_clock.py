#!/usr/bin/env python3
"""Floating analog clock widget for Linux desktops."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt
    from PyQt5.QtGui import QColor, QCursor, QFont, QFontDatabase, QPainter, QPen
    from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QMenu, QMessageBox, QWidget

    PYQT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    # Allow non-GUI commands (launcher install/uninstall) to run without PyQt.
    QPointF = QRectF = QTimer = Qt = object  # type: ignore[assignment]
    QColor = QCursor = QFont = QFontDatabase = QPainter = QPen = object  # type: ignore[assignment]
    QAction = QActionGroup = QApplication = QMenu = QMessageBox = QWidget = object  # type: ignore[assignment]
    PYQT_IMPORT_ERROR = exc


STATE_DIR = Path.home() / ".config" / "dt_clock"
STATE_FILE = STATE_DIR / "state.json"
APP_ID = "dt-clock"
APP_NAME = "DT Clock"
APP_COMMENT = "Floating translucent analog desktop clock"
MENU_ENTRY_FILE = Path.home() / ".local" / "share" / "applications" / f"{APP_ID}.desktop"
AUTOSTART_FILE = Path.home() / ".config" / "autostart" / f"{APP_ID}.desktop"
KWIN_RULES_FILE = Path.home() / ".config" / "kwinrulesrc"
KWIN_RULE_GROUP = "DTClockKeepAbove"

MODE_CLOCK = "clock"
MODE_STOPWATCH = "stopwatch"
DEFAULT_MODE = MODE_CLOCK

LAYER_TOP = "top"
LAYER_NORMAL = "normal"
LAYER_BOTTOM = "bottom"
DEFAULT_LAYER = LAYER_TOP

MIN_CLOCK_SIZE = 120
MAX_CLOCK_SIZE = 640
DEFAULT_CLOCK_SIZE = 220

THEME_PRESETS = {
    "midnight": {
        "label": "Midnight",
        "face_fill": (16, 20, 28),
        "face_border": (240, 244, 250, 205),
        "major_tick": (252, 252, 252, 230),
        "minor_tick": (235, 235, 235, 140),
        "text_primary": (255, 255, 255, 182),
        "text_secondary": (255, 255, 255, 170),
        "hand_primary": (255, 255, 255, 240),
        "hand_secondary": (255, 255, 255, 220),
        "hand_accent": (255, 96, 96, 245),
        "center_dot": (245, 247, 250, 230),
        "readout_bg": (8, 12, 18, 118),
        "readout_border": (240, 244, 250, 130),
        "readout_label": (232, 236, 244, 200),
        "readout_text": (248, 250, 255, 245),
    },
    "daylight": {
        "label": "Daylight",
        "face_fill": (250, 252, 255),
        "face_border": (38, 54, 79, 190),
        "major_tick": (40, 58, 85, 220),
        "minor_tick": (60, 80, 110, 130),
        "text_primary": (25, 35, 50, 210),
        "text_secondary": (40, 52, 70, 185),
        "hand_primary": (22, 39, 61, 235),
        "hand_secondary": (45, 68, 95, 220),
        "hand_accent": (206, 62, 43, 240),
        "center_dot": (20, 34, 54, 220),
        "readout_bg": (255, 255, 255, 170),
        "readout_border": (50, 72, 103, 150),
        "readout_label": (28, 44, 65, 210),
        "readout_text": (15, 27, 40, 245),
    },
    "high_contrast": {
        "label": "High Contrast",
        "face_fill": (0, 0, 0),
        "face_border": (255, 255, 255, 230),
        "major_tick": (255, 255, 255, 240),
        "minor_tick": (190, 190, 190, 175),
        "text_primary": (255, 255, 255, 240),
        "text_secondary": (255, 255, 255, 210),
        "hand_primary": (255, 255, 255, 250),
        "hand_secondary": (200, 255, 255, 240),
        "hand_accent": (255, 214, 0, 250),
        "center_dot": (255, 255, 255, 255),
        "readout_bg": (0, 0, 0, 185),
        "readout_border": (255, 255, 255, 170),
        "readout_label": (255, 255, 255, 230),
        "readout_text": (255, 214, 0, 255),
    },
    "ocean": {
        "label": "Ocean",
        "face_fill": (14, 35, 46),
        "face_border": (186, 241, 255, 200),
        "major_tick": (194, 244, 255, 225),
        "minor_tick": (123, 180, 194, 145),
        "text_primary": (213, 247, 255, 205),
        "text_secondary": (186, 231, 245, 190),
        "hand_primary": (226, 253, 255, 240),
        "hand_secondary": (166, 219, 235, 225),
        "hand_accent": (95, 255, 196, 240),
        "center_dot": (222, 255, 246, 235),
        "readout_bg": (8, 28, 38, 128),
        "readout_border": (175, 237, 255, 140),
        "readout_label": (200, 244, 255, 210),
        "readout_text": (225, 255, 247, 250),
    },
}
THEME_ORDER = ["midnight", "daylight", "high_contrast", "ocean"]
DEFAULT_THEME = "midnight"

PREFERRED_READOUT_FONTS = [
    "JetBrains Mono",
    "Fira Code",
    "Noto Sans Mono",
    "MesloLGS Nerd Font Mono",
    "MesloLGSDZ Nerd Font Mono",
    "DejaVu Sans Mono",
    "Adwaita Mono",
]
DEFAULT_READOUT_FONT = "Monospace"


def _clamp_opacity(value: float) -> float:
    return max(0.05, min(value, 0.95))


def _desktop_escape(value: str) -> str:
    needs_quotes = any(ch.isspace() for ch in value) or any(ch in ('"', "\\", "$", "`") for ch in value)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return f'"{escaped}"' if needs_quotes else escaped


def _valid_mode(mode: str | None) -> str:
    if mode in (MODE_CLOCK, MODE_STOPWATCH):
        return mode
    return DEFAULT_MODE


def _valid_layer(layer: str | None) -> str:
    if layer in (LAYER_TOP, LAYER_NORMAL, LAYER_BOTTOM):
        return layer
    return DEFAULT_LAYER


def _valid_theme(theme_name: str | None) -> str:
    if theme_name in THEME_PRESETS:
        return theme_name
    return DEFAULT_THEME


def _valid_size(size: int | str | None) -> int:
    try:
        parsed = int(size)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = DEFAULT_CLOCK_SIZE
    return max(MIN_CLOCK_SIZE, min(MAX_CLOCK_SIZE, parsed))


def _qcolor(values: tuple[int, ...]) -> QColor:
    if len(values) == 3:
        return QColor(values[0], values[1], values[2])
    return QColor(values[0], values[1], values[2], values[3])


def _normalize_readout_font(font_name: str | None) -> str:
    if not isinstance(font_name, str):
        return DEFAULT_READOUT_FONT
    normalized = font_name.strip()
    return normalized if normalized else DEFAULT_READOUT_FONT


def get_readout_font_choices(max_dynamic_fonts: int = 28) -> list[str]:
    if PYQT_IMPORT_ERROR is not None:
        return [DEFAULT_READOUT_FONT]
    if QApplication.instance() is None:
        return [DEFAULT_READOUT_FONT]

    db = QFontDatabase()
    families = sorted(set(db.families()))

    choices: list[str] = []
    for preferred in PREFERRED_READOUT_FONTS:
        if preferred in families and preferred not in choices:
            choices.append(preferred)

    dynamic_fixed = [family for family in families if db.isFixedPitch(family) and family not in choices]
    choices.extend(dynamic_fixed[:max_dynamic_fonts])

    if DEFAULT_READOUT_FONT not in choices:
        choices.append(DEFAULT_READOUT_FONT)

    return choices


def load_saved_state() -> dict:
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def build_launch_command(
    size: int,
    opacity: float,
    hide_seconds: bool,
    layer: str,
    mode: str,
    theme: str,
    readout_font: str,
) -> list[str]:
    python_path = str(Path(sys.executable).resolve()) if sys.executable else "/usr/bin/python3"
    normalized_layer = _valid_layer(layer)
    command = [
        python_path,
        str(Path(__file__).resolve()),
        "--size",
        str(_valid_size(size)),
        "--opacity",
        f"{_clamp_opacity(opacity):.2f}",
        "--mode",
        _valid_mode(mode),
        "--theme",
        _valid_theme(theme),
        "--readout-font",
        _normalize_readout_font(readout_font),
    ]
    if normalized_layer == LAYER_BOTTOM:
        command.append("--on-bottom")
    elif normalized_layer == LAYER_NORMAL:
        command.append("--normal-layer")
    else:
        command.append("--on-top")
    if hide_seconds:
        command.append("--hide-seconds")
    return command


def build_desktop_entry(launch_command: list[str], autostart: bool) -> str:
    exec_line = " ".join(_desktop_escape(part) for part in launch_command)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        f"Comment={APP_COMMENT}",
        f"Exec={exec_line}",
        "Terminal=false",
        "Icon=clock",
        "Categories=Utility;",
        "StartupNotify=false",
    ]
    if autostart:
        lines.extend(
            [
                "Hidden=false",
                "NoDisplay=false",
                "X-GNOME-Autostart-enabled=true",
            ]
        )
    return "\n".join(lines) + "\n"


def write_desktop_entry(path: Path, launch_command: list[str], autostart: bool) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_desktop_entry(launch_command, autostart), encoding="utf-8")
        return True
    except OSError:
        return False


def set_desktop_entry_enabled(
    path: Path, enabled: bool, launch_command: list[str], autostart: bool
) -> bool:
    if enabled:
        return write_desktop_entry(path, launch_command, autostart)

    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _resolve_kwin_tools() -> tuple[str, str] | None:
    kwrite = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    kread = shutil.which("kreadconfig6") or shutil.which("kreadconfig5")
    if not kwrite or not kread:
        return None
    return kwrite, kread


def _is_kde_session() -> bool:
    desktop = f"{os.getenv('XDG_CURRENT_DESKTOP', '')} {os.getenv('DESKTOP_SESSION', '')}".lower()
    return "kde" in desktop or "plasma" in desktop


def _run_tool(args: list[str]) -> tuple[bool, str, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        return False, "", str(exc)
    return completed.returncode == 0, completed.stdout.strip(), completed.stderr.strip()


def _kread_value(kread_bin: str, group: str, key: str, default: str = "") -> str:
    ok, out, _ = _run_tool(
        [
            kread_bin,
            "--file",
            str(KWIN_RULES_FILE),
            "--group",
            group,
            "--key",
            key,
            "--default",
            default,
        ]
    )
    return out if ok else default


def _kwrite_value(kwrite_bin: str, group: str, key: str, value: str, value_type: str | None = None) -> bool:
    cmd = [
        kwrite_bin,
        "--file",
        str(KWIN_RULES_FILE),
        "--group",
        group,
        "--key",
        key,
    ]
    if value_type:
        cmd.extend(["--type", value_type])
    cmd.append(value)
    ok, _, _ = _run_tool(cmd)
    return ok


def _kwrite_delete(kwrite_bin: str, group: str, key: str) -> bool:
    ok, _, _ = _run_tool(
        [
            kwrite_bin,
            "--file",
            str(KWIN_RULES_FILE),
            "--group",
            group,
            "--key",
            key,
            "--delete",
            "",
        ]
    )
    return ok


def _get_kwin_rule_groups(kread_bin: str) -> list[str]:
    raw = _kread_value(kread_bin, "General", "rules", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _set_kwin_rule_groups(kwrite_bin: str, groups: list[str]) -> bool:
    deduped: list[str] = []
    for group in groups:
        if group and group not in deduped:
            deduped.append(group)

    list_ok = _kwrite_value(kwrite_bin, "General", "rules", ",".join(deduped))
    count_ok = _kwrite_value(kwrite_bin, "General", "count", str(len(deduped)))
    return list_ok and count_ok


def reload_kwin_rules() -> bool:
    for tool_name in ("qdbus6", "qdbus"):
        tool_path = shutil.which(tool_name)
        if not tool_path:
            continue
        ok, _, _ = _run_tool([tool_path, "org.kde.KWin", "/KWin", "reconfigure"])
        if ok:
            return True
    return False


def is_kwin_rule_enabled() -> bool:
    tools = _resolve_kwin_tools()
    if not tools:
        return False
    _, kread_bin = tools
    return KWIN_RULE_GROUP in _get_kwin_rule_groups(kread_bin)


def install_kwin_keep_above_rule() -> tuple[bool, str]:
    tools = _resolve_kwin_tools()
    if not tools:
        return False, "KWin helper tools (kreadconfig/kwriteconfig) were not found."

    kwrite_bin, kread_bin = tools
    write_ops = [
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "Description", "DT Clock Keep Above"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "above", "true", "bool"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "aboverule", "2"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "layer", "above"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "layerrule", "2"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "title", APP_NAME),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "titlematch", "1"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "wmclass", APP_ID),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "wmclasscomplete", "false", "bool"),
        _kwrite_value(kwrite_bin, KWIN_RULE_GROUP, "wmclassmatch", "1"),
    ]
    if not all(write_ops):
        return False, f"Failed writing KWin rule in {KWIN_RULES_FILE}."

    groups = _get_kwin_rule_groups(kread_bin)
    if KWIN_RULE_GROUP not in groups:
        groups.append(KWIN_RULE_GROUP)
    if not _set_kwin_rule_groups(kwrite_bin, groups):
        return False, f"Failed updating KWin rule list in {KWIN_RULES_FILE}."

    reloaded = reload_kwin_rules()
    if reloaded:
        return True, "Installed KWin keep-above rule and reloaded KWin rules."
    return True, "Installed KWin keep-above rule. Log out/in if it does not apply immediately."


def remove_kwin_keep_above_rule() -> tuple[bool, str]:
    tools = _resolve_kwin_tools()
    if not tools:
        return False, "KWin helper tools (kreadconfig/kwriteconfig) were not found."

    kwrite_bin, kread_bin = tools
    groups = [group for group in _get_kwin_rule_groups(kread_bin) if group != KWIN_RULE_GROUP]
    if not _set_kwin_rule_groups(kwrite_bin, groups):
        return False, f"Failed updating KWin rule list in {KWIN_RULES_FILE}."

    delete_keys = [
        "Description",
        "above",
        "aboverule",
        "layer",
        "layerrule",
        "title",
        "titlematch",
        "wmclass",
        "wmclasscomplete",
        "wmclassmatch",
    ]
    for key in delete_keys:
        _kwrite_delete(kwrite_bin, KWIN_RULE_GROUP, key)

    reloaded = reload_kwin_rules()
    if reloaded:
        return True, "Removed KWin keep-above rule and reloaded KWin rules."
    return True, "Removed KWin keep-above rule. Log out/in if it does not apply immediately."


def handle_install_flags(args: argparse.Namespace, launch_command: list[str]) -> int | None:
    requested = False
    success = True

    if args.install_menu_entry:
        requested = True
        ok = set_desktop_entry_enabled(MENU_ENTRY_FILE, True, launch_command, autostart=False)
        success = success and ok
        target = MENU_ENTRY_FILE
        print(f"Installed app menu launcher: {target}" if ok else f"Failed to install app menu launcher: {target}")

    if args.uninstall_menu_entry:
        requested = True
        ok = set_desktop_entry_enabled(MENU_ENTRY_FILE, False, launch_command, autostart=False)
        success = success and ok
        target = MENU_ENTRY_FILE
        print(
            f"Removed app menu launcher: {target}" if ok else f"Failed to remove app menu launcher: {target}"
        )

    if args.install_autostart:
        requested = True
        ok = set_desktop_entry_enabled(AUTOSTART_FILE, True, launch_command, autostart=True)
        success = success and ok
        target = AUTOSTART_FILE
        print(f"Enabled autostart: {target}" if ok else f"Failed to enable autostart: {target}")

    if args.uninstall_autostart:
        requested = True
        ok = set_desktop_entry_enabled(AUTOSTART_FILE, False, launch_command, autostart=True)
        success = success and ok
        target = AUTOSTART_FILE
        print(f"Disabled autostart: {target}" if ok else f"Failed to disable autostart: {target}")

    if args.install_kwin_rule:
        requested = True
        ok, message = install_kwin_keep_above_rule()
        success = success and ok
        print(message)

    if args.uninstall_kwin_rule:
        requested = True
        ok, message = remove_kwin_keep_above_rule()
        success = success and ok
        print(message)

    if requested:
        return 0 if success else 1
    return None


class FloatingAnalogClock(QWidget):
    def __init__(
        self,
        size: int,
        face_alpha: float,
        show_seconds: bool,
        layer: str,
        mode: str,
        color_theme: str,
        readout_font: str,
    ):
        super().__init__()
        self.clock_size = _valid_size(size)
        self.readout_height = max(52, self.clock_size // 4)
        self.layer = _valid_layer(layer)
        self.show_seconds = show_seconds
        self.face_alpha = _clamp_opacity(face_alpha)

        self.mode = _valid_mode(mode)
        self.color_theme = _valid_theme(color_theme)
        self.readout_font_family = _normalize_readout_font(readout_font)
        self.available_readout_fonts = get_readout_font_choices()

        self.stopwatch_running = False
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_start_time = 0.0

        self.drag_offset = None
        self.press_global_pos = None
        self.drag_started = False
        self.click_threshold_px = 6

        self._set_window_flags(self.layer)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._apply_window_size()
        self.setWindowTitle(APP_NAME)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self._update_refresh_timer()

    def _set_window_flags(self, layer: str) -> None:
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, layer == LAYER_TOP)
        self.setWindowFlag(Qt.WindowStaysOnBottomHint, layer == LAYER_BOTTOM)

    def _apply_window_size(self) -> None:
        extra_height = self.readout_height if self.mode == MODE_STOPWATCH else 0
        self.setFixedSize(self.clock_size, self.clock_size + extra_height)

    def _update_refresh_timer(self) -> None:
        if self.mode == MODE_STOPWATCH:
            interval_ms = 10 if self.stopwatch_running else 33
        else:
            interval_ms = 1000
        self.timer.start(interval_ms)

    def _runtime_launch_command(self) -> list[str]:
        return build_launch_command(
            size=self.clock_size,
            opacity=self.face_alpha,
            hide_seconds=not self.show_seconds,
            layer=self.layer,
            mode=self.mode,
            theme=self.color_theme,
            readout_font=self.readout_font_family,
        )

    def _current_screen(self):
        screen = None
        handle = self.windowHandle()
        if handle is not None:
            screen = handle.screen()
        if screen is None:
            screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen

    def center_on_screen(self) -> None:
        screen = self._current_screen()
        if not screen:
            return
        geometry = screen.geometry()
        self.move(
            geometry.left() + (geometry.width() - self.width()) // 2,
            geometry.top() + (geometry.height() - self.height()) // 2,
        )
        self.save_state()

    def save_state(self) -> None:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "x": self.x(),
                "y": self.y(),
                "size": self.clock_size,
                "mode": self.mode,
                "layer": self.layer,
                "theme": self.color_theme,
                "readout_font": self.readout_font_family,
            }
            STATE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass

    def restore_position(self, cli_x: int | None, cli_y: int | None, state: dict) -> None:
        if cli_x is not None and cli_y is not None:
            self.move(cli_x, cli_y)
            return

        try:
            self.move(int(state["x"]), int(state["y"]))
        except (TypeError, ValueError, KeyError):
            self.center_on_screen()
            return

        if not self._is_on_any_screen():
            self.center_on_screen()

    def _is_on_any_screen(self) -> bool:
        rect = self.frameGeometry()
        center = rect.center()
        return any(screen.geometry().contains(center) for screen in QApplication.screens())

    def set_mode(self, mode: str, persist: bool = True) -> None:
        normalized_mode = _valid_mode(mode)
        if normalized_mode == self.mode:
            return

        if normalized_mode != MODE_STOPWATCH and self.stopwatch_running:
            self.stopwatch_elapsed_ms = self._current_stopwatch_ms()
            self.stopwatch_running = False

        self.mode = normalized_mode
        self._apply_window_size()
        self._update_refresh_timer()
        self.update()
        if persist:
            self.save_state()

    def set_layer(self, layer: str, persist: bool = True, force: bool = False) -> None:
        normalized_layer = _valid_layer(layer)
        if normalized_layer == self.layer and not force:
            return

        old_geometry = self.geometry()
        was_visible = self.isVisible()
        self.layer = normalized_layer
        if was_visible:
            self.hide()

        self._set_window_flags(normalized_layer)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(old_geometry)

        if was_visible:
            self.show()

        if normalized_layer == LAYER_TOP:
            self.raise_()
            self.activateWindow()
        self.update()
        if persist:
            self.save_state()

    def set_clock_size(self, size: int, persist: bool = True) -> None:
        normalized_size = _valid_size(size)
        if normalized_size == self.clock_size:
            return

        old_center = self.frameGeometry().center()
        self.clock_size = normalized_size
        self.readout_height = max(52, self.clock_size // 4)
        self._apply_window_size()
        self.move(
            old_center.x() - self.width() // 2,
            old_center.y() - self.height() // 2,
        )
        if not self._is_on_any_screen():
            self.center_on_screen()
        self.update()
        self.repaint()
        if persist:
            self.save_state()

    def set_color_theme(self, theme_name: str, persist: bool = True) -> None:
        normalized_theme = _valid_theme(theme_name)
        if normalized_theme == self.color_theme:
            return
        self.color_theme = normalized_theme
        self.update()
        self.repaint()
        if persist:
            self.save_state()

    def set_readout_font(self, font_family: str, persist: bool = True) -> None:
        normalized = _normalize_readout_font(font_family)
        if normalized == self.readout_font_family:
            return
        self.readout_font_family = normalized
        self.update()
        self.repaint()
        if persist:
            self.save_state()

    def _toggle_kwin_rule(self, action: QAction, checked: bool) -> None:
        if checked:
            ok, message = install_kwin_keep_above_rule()
            if ok:
                self.set_layer(LAYER_TOP)
        else:
            ok, message = remove_kwin_keep_above_rule()

        if not ok:
            action.blockSignals(True)
            action.setChecked(not checked)
            action.blockSignals(False)
            QMessageBox.warning(self, "KWin Helper Error", message)
            return

        QMessageBox.information(self, "KWin Helper", message)

    def _reload_kwin_rules_with_feedback(self) -> None:
        if reload_kwin_rules():
            QMessageBox.information(self, "KWin Helper", "KWin rules were reloaded.")
            return
        QMessageBox.warning(
            self,
            "KWin Helper",
            "Could not reload KWin rules automatically. Log out/in if needed.",
        )

    def _current_stopwatch_ms(self) -> int:
        if not self.stopwatch_running:
            return self.stopwatch_elapsed_ms
        running_ms = int((time.perf_counter() - self.stopwatch_start_time) * 1000.0)
        return self.stopwatch_elapsed_ms + max(0, running_ms)

    def toggle_stopwatch_running(self) -> None:
        if self.mode != MODE_STOPWATCH:
            return

        if self.stopwatch_running:
            self.stopwatch_elapsed_ms = self._current_stopwatch_ms()
            self.stopwatch_running = False
        else:
            self.stopwatch_start_time = time.perf_counter()
            self.stopwatch_running = True

        self._update_refresh_timer()
        self.update()

    def reset_stopwatch(self) -> None:
        self.stopwatch_elapsed_ms = 0
        if self.stopwatch_running:
            self.stopwatch_start_time = time.perf_counter()
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        menu = QMenu(self)

        mode_menu = menu.addMenu("Mode")
        mode_group = QActionGroup(mode_menu)
        mode_group.setExclusive(True)

        clock_mode_action = QAction("Clock", self)
        clock_mode_action.setCheckable(True)
        clock_mode_action.setChecked(self.mode == MODE_CLOCK)
        clock_mode_action.triggered.connect(lambda _checked=False: self.set_mode(MODE_CLOCK))
        mode_group.addAction(clock_mode_action)
        mode_menu.addAction(clock_mode_action)

        stopwatch_mode_action = QAction("Stopwatch", self)
        stopwatch_mode_action.setCheckable(True)
        stopwatch_mode_action.setChecked(self.mode == MODE_STOPWATCH)
        stopwatch_mode_action.triggered.connect(lambda _checked=False: self.set_mode(MODE_STOPWATCH))
        mode_group.addAction(stopwatch_mode_action)
        mode_menu.addAction(stopwatch_mode_action)

        if self.mode == MODE_STOPWATCH:
            start_stop_action = QAction(
                "Stop stopwatch" if self.stopwatch_running else "Start stopwatch", self
            )
            start_stop_action.triggered.connect(self.toggle_stopwatch_running)
            reset_action = QAction("Reset stopwatch", self)
            reset_action.triggered.connect(self.reset_stopwatch)
            menu.addSeparator()
            menu.addAction(start_stop_action)
            menu.addAction(reset_action)

        prefs_menu = menu.addMenu("Preferences")

        size_menu = prefs_menu.addMenu("Clock size")
        size_down_action = QAction("Smaller", self)
        size_down_action.triggered.connect(lambda: self.set_clock_size(self.clock_size - 20))
        size_down_action.setEnabled(self.clock_size > MIN_CLOCK_SIZE)
        size_menu.addAction(size_down_action)

        size_up_action = QAction("Larger", self)
        size_up_action.triggered.connect(lambda: self.set_clock_size(self.clock_size + 20))
        size_up_action.setEnabled(self.clock_size < MAX_CLOCK_SIZE)
        size_menu.addAction(size_up_action)

        size_menu.addSeparator()
        size_group = QActionGroup(size_menu)
        size_group.setExclusive(True)
        for label, size_value in [
            ("Small (160)", 160),
            ("Medium (220)", 220),
            ("Large (300)", 300),
            ("XL (380)", 380),
        ]:
            size_action = QAction(label, self)
            size_action.setCheckable(True)
            size_action.setChecked(abs(self.clock_size - size_value) <= 8)
            size_action.triggered.connect(lambda _checked=False, value=size_value: self.set_clock_size(value))
            size_group.addAction(size_action)
            size_menu.addAction(size_action)

        layer_menu = prefs_menu.addMenu("Window layer")
        layer_group = QActionGroup(layer_menu)
        layer_group.setExclusive(True)
        for label, layer_value in [
            ("Always on top", LAYER_TOP),
            ("Normal", LAYER_NORMAL),
            ("Below windows", LAYER_BOTTOM),
        ]:
            layer_action = QAction(label, self)
            layer_action.setCheckable(True)
            layer_action.setChecked(self.layer == layer_value)
            layer_action.triggered.connect(
                lambda _checked=False, value=layer_value: self.set_layer(value)
            )
            layer_group.addAction(layer_action)
            layer_menu.addAction(layer_action)

        kwin_menu = prefs_menu.addMenu("KWin helper")
        kwin_available = _is_kde_session() and _resolve_kwin_tools() is not None
        kwin_enabled = kwin_available and is_kwin_rule_enabled()

        kwin_rule_action = QAction("Enable keep-above rule", self)
        kwin_rule_action.setCheckable(True)
        kwin_rule_action.setChecked(kwin_enabled)
        kwin_rule_action.setEnabled(kwin_available)
        kwin_rule_action.triggered.connect(
            lambda checked, action=kwin_rule_action: self._toggle_kwin_rule(action, checked)
        )
        kwin_menu.addAction(kwin_rule_action)

        reload_kwin_action = QAction("Reload KWin rules", self)
        reload_kwin_action.setEnabled(kwin_available)
        reload_kwin_action.triggered.connect(self._reload_kwin_rules_with_feedback)
        kwin_menu.addAction(reload_kwin_action)

        if not kwin_available:
            kwin_hint_action = QAction("Unavailable outside KDE/KWin", self)
            kwin_hint_action.setEnabled(False)
            kwin_menu.addAction(kwin_hint_action)

        theme_menu = prefs_menu.addMenu("Color theme")
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        for theme_name in THEME_ORDER:
            theme_info = THEME_PRESETS[theme_name]
            theme_action = QAction(theme_info["label"], self)
            theme_action.setCheckable(True)
            theme_action.setChecked(self.color_theme == theme_name)
            theme_action.triggered.connect(
                lambda _checked=False, value=theme_name: self.set_color_theme(value)
            )
            theme_group.addAction(theme_action)
            theme_menu.addAction(theme_action)

        apps_action = QAction("Show in apps menu", self)
        apps_action.setCheckable(True)
        apps_action.setChecked(MENU_ENTRY_FILE.exists())
        apps_action.triggered.connect(
            lambda checked, action=apps_action: self._toggle_entry(
                action, checked, MENU_ENTRY_FILE, autostart=False
            )
        )
        prefs_menu.addAction(apps_action)

        autostart_action = QAction("Start at login", self)
        autostart_action.setCheckable(True)
        autostart_action.setChecked(AUTOSTART_FILE.exists())
        autostart_action.triggered.connect(
            lambda checked, action=autostart_action: self._toggle_entry(
                action, checked, AUTOSTART_FILE, autostart=True
            )
        )
        prefs_menu.addAction(autostart_action)

        font_menu = prefs_menu.addMenu("Readout font")
        font_group = QActionGroup(font_menu)
        font_group.setExclusive(True)

        font_choices = list(self.available_readout_fonts)
        if self.readout_font_family not in font_choices:
            font_choices.insert(0, self.readout_font_family)

        for family in font_choices:
            font_action = QAction(family, self)
            font_action.setCheckable(True)
            font_action.setChecked(self.readout_font_family == family)
            font_action.triggered.connect(lambda _checked=False, f=family: self.set_readout_font(f))
            font_group.addAction(font_action)
            font_menu.addAction(font_action)

        menu.addSeparator()
        center_action = QAction("Center on screen", self)
        quit_action = QAction("Quit", self)
        center_action.triggered.connect(self.center_on_screen)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(center_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        menu.exec_(event.globalPos())

    def _toggle_entry(self, action: QAction, checked: bool, path: Path, autostart: bool) -> None:
        ok = set_desktop_entry_enabled(
            path, checked, self._runtime_launch_command(), autostart=autostart
        )
        if ok:
            return

        action.blockSignals(True)
        action.setChecked(not checked)
        action.blockSignals(False)
        QMessageBox.warning(self, "Preference Error", f"Could not update:\n{path}")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if event.button() != Qt.LeftButton:
            return

        self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        self.press_global_pos = event.globalPos()
        self.drag_started = False

        if self.mode == MODE_CLOCK:
            # Wayland compositors often block client-side move(); request system move first.
            window_handle = self.windowHandle()
            if window_handle is not None and hasattr(window_handle, "startSystemMove"):
                if window_handle.startSystemMove():
                    self.drag_started = True
                    self.drag_offset = None
                    event.accept()
                    return

        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self.drag_offset is None or not (event.buttons() & Qt.LeftButton):
            return

        if not self.drag_started and self.press_global_pos is not None:
            drag_distance = (event.globalPos() - self.press_global_pos).manhattanLength()
            if drag_distance > self.click_threshold_px:
                self.drag_started = True

        if self.drag_started:
            self.move(event.globalPos() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if event.button() != Qt.LeftButton:
            return

        was_click = False
        if self.press_global_pos is not None:
            distance = (event.globalPos() - self.press_global_pos).manhattanLength()
            was_click = distance <= self.click_threshold_px and not self.drag_started

        if self.mode == MODE_STOPWATCH and was_click:
            self.toggle_stopwatch_running()

        if self.drag_started:
            self.save_state()

        self.drag_offset = None
        self.press_global_pos = None
        self.drag_started = False
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt signature)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = THEME_PRESETS[_valid_theme(self.color_theme)]

        face_bounds = QRectF(4, 4, self.clock_size - 8, self.clock_size - 8)
        center = face_bounds.center()
        radius = min(face_bounds.width(), face_bounds.height()) / 2

        face = _qcolor(palette["face_fill"])
        face.setAlphaF(self.face_alpha)
        painter.setPen(QPen(_qcolor(palette["face_border"]), 2))
        painter.setBrush(face)
        painter.drawEllipse(face_bounds)

        if self.mode == MODE_STOPWATCH:
            self._draw_stopwatch_tick_marks(painter, center, radius, palette)
            self._draw_stopwatch_hands(painter, center, radius, palette)
        else:
            self._draw_clock_tick_marks(painter, center, radius, palette)
            self._draw_clock_hands(painter, center, radius, palette)

        painter.setPen(Qt.NoPen)
        painter.setBrush(_qcolor(palette["center_dot"]))
        painter.drawEllipse(center, 4, 4)

        if self.mode == MODE_STOPWATCH:
            self._draw_stopwatch_readout(painter, palette)

    def _draw_clock_tick_marks(
        self, painter: QPainter, center: QPointF, radius: float, palette: dict
    ) -> None:
        for step in range(60):
            angle = math.radians(step * 6 - 90)
            outer = QPointF(
                center.x() + (radius - 10) * math.cos(angle),
                center.y() + (radius - 10) * math.sin(angle),
            )

            if step % 5 == 0:
                inner_distance = radius - 24
                thickness = 2.6
                color = _qcolor(palette["major_tick"])
            else:
                inner_distance = radius - 18
                thickness = 1.2
                color = _qcolor(palette["minor_tick"])

            inner = QPointF(
                center.x() + inner_distance * math.cos(angle),
                center.y() + inner_distance * math.sin(angle),
            )
            painter.setPen(QPen(color, thickness))
            painter.drawLine(inner, outer)

        painter.setPen(_qcolor(palette["text_primary"]))
        painter.setFont(QFont("Noto Sans", max(8, self.clock_size // 20)))
        for hour in range(1, 13):
            angle = math.radians(hour * 30 - 90)
            text_radius = radius - 38
            x = center.x() + text_radius * math.cos(angle)
            y = center.y() + text_radius * math.sin(angle)
            painter.drawText(int(x - 6), int(y + 5), str(hour))

    def _draw_stopwatch_tick_marks(
        self, painter: QPainter, center: QPointF, radius: float, palette: dict
    ) -> None:
        for step in range(60):
            angle = math.radians(step * 6 - 90)
            outer = QPointF(
                center.x() + (radius - 10) * math.cos(angle),
                center.y() + (radius - 10) * math.sin(angle),
            )

            if step % 5 == 0:
                inner_distance = radius - 25
                thickness = 2.4
                color = _qcolor(palette["major_tick"])
            else:
                inner_distance = radius - 17
                thickness = 1.2
                color = _qcolor(palette["minor_tick"])

            inner = QPointF(
                center.x() + inner_distance * math.cos(angle),
                center.y() + inner_distance * math.sin(angle),
            )
            painter.setPen(QPen(color, thickness))
            painter.drawLine(inner, outer)

        painter.setPen(_qcolor(palette["text_secondary"]))
        painter.setFont(QFont("Noto Sans", max(7, self.clock_size // 24)))
        for seconds_mark in range(5, 61, 5):
            angle = math.radians((seconds_mark % 60) * 6 - 90)
            text_radius = radius - 37
            x = center.x() + text_radius * math.cos(angle)
            y = center.y() + text_radius * math.sin(angle)
            painter.drawText(int(x - 8), int(y + 4), "60" if seconds_mark == 60 else str(seconds_mark))

    def _draw_clock_hands(
        self, painter: QPainter, center: QPointF, radius: float, palette: dict
    ) -> None:
        now = datetime.now()
        hour = (now.hour % 12) + now.minute / 60.0 + now.second / 3600.0
        minute = now.minute + now.second / 60.0
        second = now.second

        self._draw_hand(
            painter,
            center,
            angle_deg=hour * 30 - 90,
            length=radius * 0.50,
            width=4,
            color=_qcolor(palette["hand_primary"]),
        )
        self._draw_hand(
            painter,
            center,
            angle_deg=minute * 6 - 90,
            length=radius * 0.72,
            width=3,
            color=_qcolor(palette["hand_secondary"]),
        )
        if self.show_seconds:
            self._draw_hand(
                painter,
                center,
                angle_deg=second * 6 - 90,
                length=radius * 0.82,
                width=1,
                color=_qcolor(palette["hand_accent"]),
            )

    def _draw_stopwatch_hands(
        self, painter: QPainter, center: QPointF, radius: float, palette: dict
    ) -> None:
        elapsed_ms = self._current_stopwatch_ms()
        elapsed_seconds = elapsed_ms / 1000.0
        elapsed_minutes = elapsed_ms / 60000.0
        elapsed_hours = elapsed_ms / 3600000.0

        self._draw_hand(
            painter,
            center,
            angle_deg=(elapsed_hours % 12.0) * 30 - 90,
            length=radius * 0.44,
            width=3,
            color=_qcolor(palette["hand_secondary"]),
        )
        self._draw_hand(
            painter,
            center,
            angle_deg=(elapsed_minutes % 60.0) * 6 - 90,
            length=radius * 0.68,
            width=3,
            color=_qcolor(palette["hand_primary"]),
        )
        self._draw_hand(
            painter,
            center,
            angle_deg=(elapsed_seconds % 60.0) * 6 - 90,
            length=radius * 0.82,
            width=1.2,
            color=_qcolor(palette["hand_accent"]),
        )

    def _draw_stopwatch_readout(self, painter: QPainter, palette: dict) -> None:
        readout_rect = QRectF(
            14,
            self.clock_size + 8,
            self.clock_size - 28,
            self.readout_height - 14,
        )
        painter.setPen(QPen(_qcolor(palette["readout_border"]), 1.4))
        painter.setBrush(_qcolor(palette["readout_bg"]))
        painter.drawRoundedRect(readout_rect, 11, 11)

        status_text = "RUNNING" if self.stopwatch_running else "PAUSED"
        label_rect = QRectF(readout_rect.left(), readout_rect.top() + 4, readout_rect.width(), 16)
        painter.setPen(_qcolor(palette["readout_label"]))
        painter.setFont(QFont("Noto Sans", max(7, self.clock_size // 28)))
        painter.drawText(label_rect, int(Qt.AlignHCenter | Qt.AlignVCenter), f"STOPWATCH • {status_text}")

        elapsed_text = self._format_stopwatch_elapsed(self._current_stopwatch_ms())
        time_rect = QRectF(
            readout_rect.left() + 8,
            readout_rect.top() + 20,
            readout_rect.width() - 16,
            max(16.0, readout_rect.height() - 24),
        )
        time_font = QFont(self.readout_font_family, max(11, self.clock_size // 15))
        time_font.setStyleHint(QFont.TypeWriter)
        painter.setPen(_qcolor(palette["readout_text"]))
        painter.setFont(time_font)
        painter.drawText(time_rect, int(Qt.AlignHCenter | Qt.AlignVCenter), elapsed_text)

    @staticmethod
    def _format_stopwatch_elapsed(elapsed_ms: int) -> str:
        hours = elapsed_ms // 3_600_000
        minutes = (elapsed_ms // 60_000) % 60
        seconds = (elapsed_ms // 1_000) % 60
        millis = elapsed_ms % 1_000
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"
        return f"{minutes:02}:{seconds:02}.{millis:03}"

    @staticmethod
    def _draw_hand(
        painter: QPainter,
        center: QPointF,
        angle_deg: float,
        length: float,
        width: float,
        color: QColor,
    ) -> None:
        angle = math.radians(angle_deg)
        endpoint = QPointF(
            center.x() + length * math.cos(angle),
            center.y() + length * math.sin(angle),
        )
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(center, endpoint)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Floating analog clock and stopwatch widget.")
    parser.add_argument(
        "--size",
        type=int,
        help=f"Clock size in pixels ({MIN_CLOCK_SIZE}-{MAX_CLOCK_SIZE}).",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=0.45,
        help="Clock face opacity between 0.05 and 0.95.",
    )
    parser.add_argument(
        "--hide-seconds",
        action="store_true",
        help="Hide the seconds hand in clock mode.",
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_CLOCK, MODE_STOPWATCH],
        help="Launch mode.",
    )
    parser.add_argument(
        "--theme",
        choices=sorted(THEME_PRESETS.keys()),
        help="Color theme preset.",
    )
    parser.add_argument(
        "--readout-font",
        help="Stopwatch readout font family.",
    )
    parser.add_argument("--x", type=int, help="Initial X position.")
    parser.add_argument("--y", type=int, help="Initial Y position.")
    parser.add_argument(
        "--install-menu-entry",
        action="store_true",
        help="Install user-level launcher into the desktop apps menu.",
    )
    parser.add_argument(
        "--uninstall-menu-entry",
        action="store_true",
        help="Remove user-level launcher from the desktop apps menu.",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Enable user-level autostart entry.",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Disable user-level autostart entry.",
    )
    parser.add_argument(
        "--install-kwin-rule",
        action="store_true",
        help="Install a KWin keep-above rule for DT Clock (KDE/KWin).",
    )
    parser.add_argument(
        "--uninstall-kwin-rule",
        action="store_true",
        help="Remove the KWin keep-above rule for DT Clock.",
    )

    layer_group = parser.add_mutually_exclusive_group()
    layer_group.add_argument(
        "--on-top",
        dest="layer",
        action="store_const",
        const=LAYER_TOP,
        help="Keep clock above other windows (default).",
    )
    layer_group.add_argument(
        "--normal-layer",
        dest="layer",
        action="store_const",
        const=LAYER_NORMAL,
        help="Use normal window layer (not always on top).",
    )
    layer_group.add_argument(
        "--on-bottom",
        dest="layer",
        action="store_const",
        const=LAYER_BOTTOM,
        help="Ask the window manager to keep it below normal windows.",
    )
    parser.set_defaults(layer=None)
    args = parser.parse_args()

    if args.install_menu_entry and args.uninstall_menu_entry:
        parser.error("Choose only one of --install-menu-entry or --uninstall-menu-entry.")
    if args.install_autostart and args.uninstall_autostart:
        parser.error("Choose only one of --install-autostart or --uninstall-autostart.")
    if args.install_kwin_rule and args.uninstall_kwin_rule:
        parser.error("Choose only one of --install-kwin-rule or --uninstall-kwin-rule.")
    return args


def main() -> int:
    args = parse_args()
    saved_state = load_saved_state()

    launch_size = _valid_size(args.size if args.size is not None else saved_state.get("size"))
    launch_mode = _valid_mode(args.mode if args.mode else saved_state.get("mode"))
    launch_layer = _valid_layer(args.layer if args.layer else saved_state.get("layer"))
    launch_theme = _valid_theme(args.theme if args.theme else saved_state.get("theme"))
    launch_font = _normalize_readout_font(
        args.readout_font if args.readout_font else saved_state.get("readout_font")
    )

    launch_command = build_launch_command(
        size=launch_size,
        opacity=args.opacity,
        hide_seconds=args.hide_seconds,
        layer=launch_layer,
        mode=launch_mode,
        theme=launch_theme,
        readout_font=launch_font,
    )
    install_exit = handle_install_flags(args, launch_command)
    if install_exit is not None:
        return install_exit
    if PYQT_IMPORT_ERROR is not None:
        print("PyQt5 is required to run the clock UI. Install with: sudo pacman -S python-pyqt5")
        return 1

    app = QApplication([])

    clock = FloatingAnalogClock(
        size=launch_size,
        face_alpha=args.opacity,
        show_seconds=not args.hide_seconds,
        layer=launch_layer,
        mode=launch_mode,
        color_theme=launch_theme,
        readout_font=launch_font,
    )
    clock.restore_position(args.x, args.y, saved_state)
    clock.show()
    clock.set_layer(launch_layer, persist=False, force=True)

    exit_code = app.exec_()
    clock.save_state()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
