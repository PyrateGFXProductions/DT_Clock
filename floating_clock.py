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


# WINDOW MANAGER COMPATIBILITY:
# Wayland and modern X11 compositors treat frameless windows uniquely.
# We use a combination of hints to maximize compatibility for a 
# floating, always-on-top translucent widget.

try:
    from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt, QPropertyAnimation, QRect, pyqtProperty, QEasingCurve
    from PyQt5.QtGui import QColor, QCursor, QFont, QFontDatabase, QPainter, QPen, QLinearGradient, QRadialGradient, QBrush
    from PyQt5.QtWidgets import QAction, QActionGroup, QApplication, QMenu, QMessageBox, QWidget, QGraphicsDropShadowEffect

    PYQT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    # Allow non-GUI commands (launcher install/uninstall) to run without PyQt.
    QPointF = QRectF = QTimer = Qt = QPropertyAnimation = QRect = QEasingCurve = object  # type: ignore[assignment]
    pyqtProperty = lambda x: x
    QColor = QCursor = QFont = QFontDatabase = QPainter = QPen = QLinearGradient = QRadialGradient = QBrush = object  # type: ignore[assignment]
    QAction = QActionGroup = QApplication = QMenu = QMessageBox = QWidget = QGraphicsDropShadowEffect = object  # type: ignore[assignment]
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
LOG_FILE = STATE_DIR / "debug.log"

def _log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [PID {os.getpid()}] {msg}\n")
    except Exception:
        pass
    print(f">>> {msg}")

MODE_ANALOG = "analog"
MODE_DIGITAL = "digital"
DEFAULT_MODE = MODE_ANALOG

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
        "face_fill": [(16, 20, 28, 240), (8, 10, 14, 255)], # Gradient: (top, bottom)
        "face_border": (240, 244, 250, 180),
        "major_tick": (252, 252, 252, 230),
        "minor_tick": (235, 235, 235, 140),
        "text_primary": (255, 255, 255, 182),
        "text_secondary": (255, 255, 255, 170),
        "hand_primary": (255, 255, 255, 240),
        "hand_secondary": (230, 230, 230, 220),
        "hand_accent": (255, 80, 80, 245),
        "center_dot": (240, 242, 245, 250),
        "readout_bg": (8, 12, 18, 160),
        "readout_border": (240, 244, 250, 100),
        "readout_label": (232, 236, 244, 180),
        "readout_text": (248, 250, 255, 245),
        "glass_highlight": (255, 255, 255, 45),
    },
    "daylight": {
        "label": "Daylight",
        "face_fill": [(250, 252, 255, 245), (230, 235, 245, 255)],
        "face_border": (38, 54, 79, 160),
        "major_tick": (40, 58, 85, 220),
        "minor_tick": (60, 80, 110, 130),
        "text_primary": (25, 35, 50, 210),
        "text_secondary": (40, 52, 70, 185),
        "hand_primary": (22, 39, 61, 235),
        "hand_secondary": (45, 68, 95, 220),
        "hand_accent": (206, 62, 43, 240),
        "center_dot": (20, 34, 54, 220),
        "readout_bg": (255, 255, 255, 180),
        "readout_border": (50, 72, 103, 120),
        "readout_label": (28, 44, 65, 210),
        "readout_text": (15, 27, 40, 245),
        "glass_highlight": (255, 255, 255, 80),
    },
    "high_contrast": {
        "label": "High Contrast",
        "face_fill": [(10, 10, 10, 255), (0, 0, 0, 255)],
        "face_border": (255, 255, 255, 230),
        "major_tick": (255, 255, 255, 240),
        "minor_tick": (210, 210, 210, 175),
        "text_primary": (255, 255, 255, 240),
        "text_secondary": (255, 255, 255, 210),
        "hand_primary": (255, 255, 255, 250),
        "hand_secondary": (200, 255, 255, 240),
        "hand_accent": (255, 214, 0, 250),
        "center_dot": (255, 255, 255, 255),
        "readout_bg": (0, 0, 0, 200),
        "readout_border": (255, 255, 255, 170),
        "readout_label": (255, 255, 255, 230),
        "readout_text": (255, 214, 0, 255),
        "glass_highlight": (255, 255, 255, 30),
    },
    "ocean": {
        "label": "Ocean",
        "face_fill": [(14, 45, 60, 240), (8, 25, 35, 255)],
        "face_border": (186, 241, 255, 180),
        "major_tick": (194, 244, 255, 225),
        "minor_tick": (123, 180, 194, 145),
        "text_primary": (213, 247, 255, 205),
        "text_secondary": (186, 231, 245, 190),
        "hand_primary": (226, 253, 255, 240),
        "hand_secondary": (166, 219, 235, 225),
        "hand_accent": (95, 255, 196, 240),
        "center_dot": (222, 255, 246, 235),
        "readout_bg": (8, 28, 38, 160),
        "readout_border": (175, 237, 255, 120),
        "readout_label": (200, 244, 255, 210),
        "readout_text": (225, 255, 247, 250),
        "glass_highlight": (255, 255, 255, 50),
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
    if mode in ("clock", "stopwatch"): # Legacy compatibility
        return MODE_ANALOG
    if mode in (MODE_ANALOG, MODE_DIGITAL):
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


def _qcolor(values: tuple[int, ...] | list[tuple[int, ...]], alpha_scale: float = 1.0) -> QColor:
    if isinstance(values, list):
        return _qcolor(values[0], alpha_scale)
    
    r, g, b = values[0], values[1], values[2]
    a = values[3] if len(values) == 4 else 255
    scaled_a = int(max(0, min(255, a * alpha_scale)))
    return QColor(r, g, b, scaled_a)


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
    _log(f"Attempting to load state from {STATE_FILE}")
    if not STATE_FILE.exists():
        _log("State file not found.")
        return {}
    try:
        content = STATE_FILE.read_text(encoding="utf-8")
        payload = json.loads(content)
        if isinstance(payload, dict):
            _log(f"State loaded: {payload}")
            return payload
        _log(f"State file format error: {type(payload)}")
        return {}
    except (OSError, ValueError) as e:
        _log(f"State load failed: {e}")
        return {}


def build_launch_command(
    size: int,
    opacity: float,
    hide_seconds: bool,
    layer: str,
    mode: str,
    theme: str,
    readout_font: str,
    stopwatch: bool = False,
    include_settings: bool = False, # Changed default to False
) -> list[str]:
    python_path = str(Path(sys.executable).resolve()) if sys.executable else "/usr/bin/python3"
    command = [python_path, str(Path(__file__).resolve())]
    
    if not include_settings:
        return command

    normalized_layer = _valid_layer(layer)
    command.extend([
        "--size", str(_valid_size(size)),
        "--opacity", f"{_clamp_opacity(opacity):.2f}",
        "--mode", _valid_mode(mode),
        "--theme", _valid_theme(theme),
        "--readout-font", _normalize_readout_font(readout_font),
    ])
    if normalized_layer == LAYER_BOTTOM:
        command.append("--on-bottom")
    elif normalized_layer == LAYER_NORMAL:
        command.append("--normal-layer")
    else:
        command.append("--on-top")
    if hide_seconds:
        command.append("--hide-seconds")
    if stopwatch:
        command.append("--stopwatch")
    return command


def _get_project_executable() -> str:
    """Returns absolute path to floating_clock.py for reliable launchers."""
    return str(Path(__file__).resolve())


def build_desktop_entry(launch_command: list[str], autostart: bool) -> str:
    exec_line = " ".join(_desktop_escape(part) for part in launch_command)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        f"Comment={APP_COMMENT}",
        f"Exec={exec_line}",
        f"Path={Path(__file__).resolve().parent}",
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
    time.sleep(0.05)
    count_ok = _kwrite_value(kwrite_bin, "General", "count", str(len(deduped)))
    return list_ok and count_ok


def reload_kwin_rules() -> bool:
    qdbus_bin = shutil.which("qdbus6") or shutil.which("qdbus")
    if qdbus_bin:
        # Plasma 6 reconfigure
        _run_tool([qdbus_bin, "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"])
    
    # Standard DBus fallback
    try:
        subprocess.run([
            "dbus-send", "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"
        ], check=False, capture_output=True)
    except Exception:
        pass
    return True
    
    # Universal fallback
    _run_tool(["dbus-send", "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"])
    return True


def is_kwin_rule_enabled() -> bool:
    # On Wayland/KDE, we MUST use rules to avoid centering jumps during layer changes.
    # We return True here to ensure set_layer() uses the KWin rule bypass.
    if _is_kde_session() and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return True

    tools = _resolve_kwin_tools()
    if not tools:
        return False
    _, kread_bin = tools
    return KWIN_RULE_GROUP in _get_kwin_rule_groups(kread_bin)


def install_kwin_keep_above_rule(layer: str = LAYER_TOP) -> tuple[bool, str]:
    tools = _resolve_kwin_tools()
    if not tools:
        return False, "KWin helper tools were not found."

    kwrite_bin, kread_bin = tools
    
    # 1. PURGE STALE KEYS: Plasma 6 uses 'above/aboverule', not 'layer/layerrule'.
    keys_to_purge = ["layer", "layerrule", "title", "titlematch", "position", "size"]
    for k in keys_to_purge:
        _kwrite_delete(kwrite_bin, KWIN_RULE_GROUP, k)
        time.sleep(0.05) # Prevent file locking race conditions
    
    is_above = "true" if layer == LAYER_TOP else "false"
    is_below = "true" if layer == LAYER_BOTTOM else "false"
    
    # 2. SEQUENTIAL ATOMIC WRITES
    # We match by TITLE for maximum reliability on Wayland/Plasma 6.
    write_ops = [
        (KWIN_RULE_GROUP, "Description", "DT Clock Persistence"),
        (KWIN_RULE_GROUP, "above", is_above, "bool"),
        (KWIN_RULE_GROUP, "aboverule", "2"), # Index 2 = Remember
        (KWIN_RULE_GROUP, "below", is_below, "bool"),
        (KWIN_RULE_GROUP, "belowrule", "2"),
        (KWIN_RULE_GROUP, "positionrule", "2"),
        (KWIN_RULE_GROUP, "sizerule", "2"),
        (KWIN_RULE_GROUP, "title", APP_NAME), # Match 'DT Clock'
        (KWIN_RULE_GROUP, "titlematch", "1"),  # 1 = Exact match
        (KWIN_RULE_GROUP, "wmclassmatch", "0"), # Ignore wmclass
    ]
    
    for group, key, val, *vtype in write_ops:
        vt = vtype[0] if vtype else None
        if not _kwrite_value(kwrite_bin, group, key, val, vt):
            return False, f"Failed writing KWin rule key: {key}"
        time.sleep(0.05)

    # 3. FORCE REGISTRATION IN GENERAL LIST
    groups = _get_kwin_rule_groups(kread_bin)
    if KWIN_RULE_GROUP not in groups:
        groups.append(KWIN_RULE_GROUP)
    _set_kwin_rule_groups(kwrite_bin, groups)
    
    reload_kwin_rules()
    return True, f"KDE Persistence Synced (Layer: {layer})"


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

    if getattr(args, "install_menu_entry", False):
        requested = True
        ok = set_desktop_entry_enabled(MENU_ENTRY_FILE, True, launch_command, autostart=False)
        success = success and ok
        target = MENU_ENTRY_FILE
        print(f"Installed app menu launcher: {target}" if ok else f"Failed to install app menu launcher: {target}")

    if getattr(args, "uninstall_menu_entry", False):
        requested = True
        ok = set_desktop_entry_enabled(MENU_ENTRY_FILE, False, launch_command, autostart=False)
        success = success and ok
        target = MENU_ENTRY_FILE
        print(
            f"Removed app menu launcher: {target}" if ok else f"Failed to remove app menu launcher: {target}"
        )

    if getattr(args, "install_autostart", False):
        requested = True
        ok = set_desktop_entry_enabled(AUTOSTART_FILE, True, launch_command, autostart=True)
        success = success and ok
        target = AUTOSTART_FILE
        print(f"Enabled autostart: {target}" if ok else f"Failed to enable autostart: {target}")

    if getattr(args, "uninstall_autostart", False):
        requested = True
        ok = set_desktop_entry_enabled(AUTOSTART_FILE, False, launch_command, autostart=True)
        success = success and ok
        target = AUTOSTART_FILE
        print(f"Disabled autostart: {target}" if ok else f"Failed to disable autostart: {target}")

    if getattr(args, "install_kwin_rule", False):
        requested = True
        ok, message = install_kwin_keep_above_rule()
        success = success and ok
        print(message)

    if getattr(args, "uninstall_kwin_rule", False):
        requested = True
        ok, message = remove_kwin_keep_above_rule()
        success = success and ok
        print(message)

    if requested:
        return 0 if success else 1
    return None


class FloatingAnalogClock(QWidget):
    @property
    def readout_height_actual(self) -> int:
        return max(52, self.clock_size // 4)

    def __init__(
        self,
        size: int,
        face_alpha: float,
        show_seconds: bool,
        layer: str,
        mode: str,
        stopwatch_active: bool,
        color_theme: str,
        readout_font: str,
        initial_x: int = 0,
        initial_y: int = 0,
    ):
        super().__init__()
        self.fully_initialized = False
        self.clock_size = _valid_size(size)
        self.layer = _valid_layer(layer)
        self.show_seconds = show_seconds
        self.face_alpha = _clamp_opacity(face_alpha)

        self.mode = _valid_mode(mode)
        self.stopwatch_active = stopwatch_active
        self.color_theme = _valid_theme(color_theme)
        self.readout_font_family = _normalize_readout_font(readout_font)
        self.available_readout_fonts = get_readout_font_choices()

        # Set initial geometry BEFORE show() to avoid birth coordinates (0,0) clobbering state
        extra_height = self.readout_height_actual if (self.stopwatch_active and self.mode == MODE_ANALOG) else 0
        extra_width = int(self.clock_size * 0.45) if self.mode == MODE_DIGITAL else 0
        self.setGeometry(initial_x, initial_y, self.clock_size + extra_width, self.clock_size + extra_height)

        self.stopwatch_running = False
        self.stopwatch_elapsed_ms = 0
        self.stopwatch_start_time = 0.0

        self.drag_offset = None
        self.press_global_pos = None
        self.drag_started = False
        self.click_threshold_px = 15 # Increased for high-DPI reliability
        self.fully_initialized = False
        
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName(APP_ID)
        self.setWindowTitle(APP_NAME)
        
        # DEFINITIVE IDENTITY: 
        # On KDE/Wayland, the app_id must match the desktop file name.
        # We also set the WindowRole and Class for older rule matchers.
        app = QApplication.instance()
        if app:
            app.setDesktopFileName(APP_ID)
            app.setApplicationName(APP_NAME)
        self.setWindowRole(APP_ID)
        
        self._set_window_flags(self.layer)
        self._apply_window_size()
        self.setWindowTitle(APP_NAME)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self._update_refresh_timer()

        # Add drop shadow for depth
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(25)
        self.shadow.setColor(QColor(0, 0, 0, 160))
        self.shadow.setOffset(0, 4)
        self.setGraphicsEffect(self.shadow)

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(450)
        self.animation.setEasingCurve(QEasingCurve.OutQuint)

    @pyqtProperty(QRect)
    def geometry_prop(self):
        return self.geometry()

    @geometry_prop.setter
    def geometry_prop(self, value):
        self.setGeometry(value)

    def _set_window_flags(self, layer: str) -> None:
        # Standard flags for a frameless application
        flags = Qt.Window | Qt.FramelessWindowHint | Qt.CustomizeWindowHint
        
        # Tool window type is essential for avoiding taskbars and 
        # often helps with staying on top in modern Linux desktop environments.
        flags |= Qt.Tool
        
        # X11BypassWindowManagerHint is ONLY safe on X11. It breaks mapping on Wayland.
        if os.environ.get("XDG_SESSION_TYPE") != "wayland":
            flags |= Qt.X11BypassWindowManagerHint
        
        if layer == LAYER_TOP:
            flags |= Qt.WindowStaysOnTopHint
        elif layer == LAYER_BOTTOM:
            flags |= Qt.WindowStaysOnBottomHint

        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        
        # SAFETY: Only re-request translucency if we didn't just crash
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        if was_visible:
            # On Wayland/KDE, we MUST call show() after setWindowFlags 
            # because setWindowFlags() calls hide() internally.
            self.show()
            if layer == LAYER_TOP:
                self.raise_()

    def _apply_window_size(self, animated: bool = False) -> None:
        # Extra height for readout only in Analog Stopwatch mode
        extra_height = self.readout_height_actual if (self.stopwatch_active and self.mode == MODE_ANALOG) else 0
        extra_width = int(self.clock_size * 0.45) if self.mode == MODE_DIGITAL else 0
        target_size = QRect(self.x(), self.y(), self.clock_size + extra_width, self.clock_size + extra_height)
        
        if animated:
            self.animation.stop()
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(target_size)
            self.animation.start()
        else:
            self.setFixedSize(self.clock_size + extra_width, self.clock_size + extra_height)
        
        # Crucial: Some WMs drop hints when local geometry changes
        # Re-apply flags if fully initialized to "lock" the layering back in
        if self.fully_initialized:
            self._set_window_flags(self.layer)

    def moveEvent(self, event) -> None: # noqa: N802
        super().moveEvent(event)
        # We NO LONGER auto-save in moveEvent. This was clobbering 
        # good settings with Wayland's initial (0,0) mapping coordinates.
        # Position is now only saved on drag-release or manual save.
        pass

    def _update_refresh_timer(self) -> None:
        if self.stopwatch_active:
            interval_ms = 10 if self.stopwatch_running else 33
        else:
            interval_ms = 1000
        self.timer.start(interval_ms)

    def _runtime_launch_command(self, include_settings: bool = False) -> list[str]:
        return build_launch_command(
            size=self.clock_size,
            opacity=self.face_alpha,
            hide_seconds=not self.show_seconds,
            layer=self.layer,
            mode=self.mode,
            theme=self.color_theme,
            readout_font=self.readout_font_family,
            stopwatch=self.stopwatch_active,
            include_settings=include_settings,
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

    def set_face_alpha(self, alpha: float, persist: bool = True) -> None:
        self.face_alpha = _clamp_opacity(alpha)
        self.update()
        self.repaint()
        if persist:
            self.save_state()

    def save_state(self, manual: bool = False) -> None:
        # INITIALIZATION SHIELD:
        # On Wayland/KDE, we must ignore all automatic saves during the first 
        # few seconds of launch to prevent "birth coordinates" (0,0 or centering)
        # from overwriting the legitimate saved state.
        if not manual and not getattr(self, "fully_initialized", False):
            return

        try:
            # COORDINATE STRATEGY (Wayland):
            # We only reject coordinates as "garbage" if they are negative
            # or exactly (0,0) during the first few seconds of launch.
            current_x, current_y = self.x(), self.y()
            is_fresh_unplaced = current_x == 0 and current_y == 0 and not getattr(self, "fully_initialized", False)
            
            if not manual and (current_x < 0 or current_y < 0 or is_fresh_unplaced):
                saved = load_saved_state()
                current_x = saved.get("x", current_x)
                current_y = saved.get("y", current_y)
                
                # If still invalid and not manual, abort save
                if current_x < 0 or current_y < 0:
                    return

            STATE_DIR.mkdir(parents=True, exist_ok=True)
            
            # Sync stopwatch time if running
            current_elapsed = self.stopwatch_elapsed_ms
            if self.stopwatch_running:
                current_elapsed += int((time.perf_counter() - self.stopwatch_start_time) * 1000)

            payload = {
                "x": current_x,
                "y": current_y,
                "size": self.clock_size,
                "mode": self.mode,
                "stopwatch_active": self.stopwatch_active,
                "stopwatch_running": self.stopwatch_running,
                "stopwatch_elapsed": current_elapsed,
                "layer": self.layer,
                "theme": self.color_theme,
                "readout_font": self.readout_font_family,
                "opacity": self.face_alpha,
                "show_seconds": self.show_seconds,
            }
            
            _log(f"Saving state (manual={manual}): x={current_x}, y={current_y}, size={self.clock_size}, opacity={self.face_alpha:.2f}")
            
            if manual:
                # Update KWin Rule
                if is_kwin_rule_enabled():
                    install_kwin_keep_above_rule(self.layer)
            
            content = json.dumps(payload, indent=2)
            STATE_FILE.write_text(content, encoding="utf-8")
            
            if manual:
                # Visual feedback: Triple flash
                old_alpha = self.face_alpha
                def flash(a): self.set_face_alpha(a, persist=False)
                QTimer.singleShot(50, lambda: flash(0.95))
                QTimer.singleShot(200, lambda: flash(old_alpha))
                QTimer.singleShot(350, lambda: flash(0.95))
                QTimer.singleShot(500, lambda: flash(old_alpha))
                
                try:
                    subprocess.run(["notify-send", "-a", APP_NAME, "-t", "1500", "DT Clock", "Layout and Layer Saved"], check=False)
                except Exception:
                    pass
        except OSError as e:
            print(f"!!! CRITICAL: Failed to save settings: {e}")

    def restore_position(self, cli_x: int | None, cli_y: int | None, state: dict) -> None:
        # CLI arguments ALWAYS win if provided.
        if cli_x is not None and cli_y is not None:
            _log(f"RESTORE: Using explicit CLI coordinates: {cli_x},{cli_y}")
            self.move(cli_x, cli_y)
            return

        # STARTUP ANCHOR:
        try:
            target_x = state.get("x")
            target_y = state.get("y")
            if target_x is not None and target_y is not None:
                _log(f"RESTORE: Applying anchor from state: {target_x},{target_y}")
                self.move(int(target_x), int(target_y))
            else:
                _log("RESTORE: No saved position found, centering.")
                self.center_on_screen()
        except (TypeError, ValueError) as e:
            _log(f"RESTORE: Failed to parse coordinates: {e}")
            self.center_on_screen()

        # Relaxed off-screen check: On multi-monitor setups, negative coords or large 
        # offsets are common. We only center if the window is truly "lost" (e.g. > 10k pixels away).
        rect = self.frameGeometry()
        if abs(rect.x()) > 10000 or abs(rect.y()) > 10000:
            _log("RESTORE: Window position seems erroneous (lost), centering.")
            self.center_on_screen()

    def _is_on_any_screen(self) -> bool:
        rect = self.frameGeometry()
        center = rect.center()
        return any(screen.geometry().contains(center) for screen in QApplication.screens())

    def toggle_stopwatch(self) -> None:
        self.stopwatch_active = not self.stopwatch_active
        if not self.stopwatch_active and self.stopwatch_running:
            self.stopwatch_elapsed_ms = self._current_stopwatch_ms()
            self.stopwatch_running = False
        
        self._set_window_flags(self.layer)
        self._apply_window_size(animated=True)
        self._update_refresh_timer()
        self.update()
        self.save_state()

    def set_mode(self, mode: str, persist: bool = True) -> None:
        normalized_mode = _valid_mode(mode)
        if normalized_mode == self.mode:
            return

        self.mode = normalized_mode
        self._apply_window_size(animated=True)
        # Re-apply flags AFTER size change to ensure WM respects layered status
        self._set_window_flags(self.layer) 
        self._update_refresh_timer()
        self.update()
        if persist:
            self.save_state()

    def set_layer(self, layer: str, persist: bool = True, force: bool = False) -> None:
        normalized_layer = _valid_layer(layer)
        if normalized_layer == self.layer and not force:
            return

        # ANCHOR THE COORDINATES:
        # We only fallback to saved state if the current move sensors
        # are reporting impossible (negative) coordinates.
        cur_x, cur_y = self.x(), self.y()
        if cur_x < 0 or cur_y < 0:
             saved = load_saved_state()
             cur_x = saved.get("x", 0)
             cur_y = saved.get("y", 0)

        self.layer = normalized_layer
        
        # 1. SYSTEM CONTEXT (KDE/Wayland): 
        # On Wayland, Updating the KWin rule and calling reconfigure is the ONLY
        # way to change the layer WITHOUT triggering a "jump to center" caused 
        # by surface re-mapping in setWindowFlags.
        if _is_kde_session() and is_kwin_rule_enabled():
            install_kwin_keep_above_rule(normalized_layer)
            reload_kwin_rules()
            
            if os.environ.get("XDG_SESSION_TYPE") == "wayland":
                # ABSOLUTELY DO NOT call setWindowFlags on Wayland for live toggles.
                # It destroys the buffer and jumps the window.
                # KWin will apply the rule we just updated.
                if persist:
                    self.save_state()
                return

        # 2. LOCAL CONTEXT (X11 or non-KDE):
        # We use standard Qt flags. This WILL cause a jump on Wayland, 
        # which is why we return early above if on Wayland/KDE.
        was_visible = self.isVisible()
        self._set_window_flags(normalized_layer)
        
        if cur_x > 0 or cur_y > 0:
            self.move(cur_x, cur_y)

        if was_visible:
            self.show()
            # Restore position after show()
            if cur_x > 0 or cur_y > 0:
                QTimer.singleShot(200, lambda: self.move(cur_x, cur_y))

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
        if not self.stopwatch_active:
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

        save_settings_action = QAction("SAVE CURRENT LAYOUT", self)
        save_settings_action.setIconText("💾")
        save_settings_action.triggered.connect(lambda: self.save_state(manual=True))
        menu.addAction(save_settings_action)
        menu.addSeparator()

        mode_menu = menu.addMenu("Mode")
        mode_group = QActionGroup(mode_menu)
        mode_group.setExclusive(True)

        analog_mode_action = QAction("Analog Clock", self)
        analog_mode_action.setCheckable(True)
        analog_mode_action.setChecked(self.mode == MODE_ANALOG)
        analog_mode_action.triggered.connect(lambda _checked=False: self.set_mode(MODE_ANALOG))
        mode_group.addAction(analog_mode_action)
        mode_menu.addAction(analog_mode_action)

        digital_mode_action = QAction("Digital Clock", self)
        digital_mode_action.setCheckable(True)
        digital_mode_action.setChecked(self.mode == MODE_DIGITAL)
        digital_mode_action.triggered.connect(lambda _checked=False: self.set_mode(MODE_DIGITAL))
        mode_group.addAction(digital_mode_action)
        mode_menu.addAction(digital_mode_action)

        stopwatch_menu = menu.addMenu("Stopwatch")
        
        toggle_stopwatch_action = QAction("Show Stopwatch" if not self.stopwatch_active else "Hide Stopwatch", self)
        toggle_stopwatch_action.triggered.connect(self.toggle_stopwatch)
        stopwatch_menu.addAction(toggle_stopwatch_action)
        
        if self.stopwatch_active:
            start_stop_action = QAction(
                "Stop stopwatch" if self.stopwatch_running else "Start stopwatch", self
            )
            start_stop_action.triggered.connect(self.toggle_stopwatch_running)
            reset_action = QAction("Reset stopwatch", self)
            reset_action.triggered.connect(self.reset_stopwatch)
            stopwatch_menu.addSeparator()
            stopwatch_menu.addAction(start_stop_action)
            stopwatch_menu.addAction(reset_action)

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

        opacity_menu = prefs_menu.addMenu("Background opacity")
        opacity_group = QActionGroup(opacity_menu)
        opacity_group.setExclusive(True)
        for label, alpha_val in [
            ("Ghost (15%)", 0.15),
            ("Translucent (40%)", 0.40),
            ("Modern (65%)", 0.65),
            ("Bold (85%)", 0.85),
            ("Opaque (100%)", 1.0),
        ]:
            opacity_action = QAction(label, self)
            opacity_action.setCheckable(True)
            # Use a small epsilon for float comparison
            opacity_action.setChecked(abs(self.face_alpha - alpha_val) < 0.05)
            opacity_action.triggered.connect(
                lambda _checked=False, val=alpha_val: self.set_face_alpha(val)
            )
            opacity_group.addAction(opacity_action)
            opacity_menu.addAction(opacity_action)

        menu.addSeparator()
        
        # Admin / System menu
        sys_menu = menu.addMenu("System")
        center_action = QAction("Center on screen", self)
        center_action.triggered.connect(lambda: (self.center_on_screen(), self.save_state(manual=True)))
        sys_menu.addAction(center_action)
        
        sys_menu.addSeparator()
        
        apps_action = QAction("Show in apps menu", self)
        apps_action.setCheckable(True)
        apps_action.setChecked(MENU_ENTRY_FILE.exists())
        apps_action.triggered.connect(
            lambda checked, action=apps_action: self._toggle_entry(
                action, checked, MENU_ENTRY_FILE, autostart=False
            )
        )
        sys_menu.addAction(apps_action)

        autostart_action = QAction("Start at login", self)
        autostart_action.setCheckable(True)
        autostart_action.setChecked(AUTOSTART_FILE.exists())
        autostart_action.triggered.connect(
            lambda checked, action=autostart_action: self._toggle_entry(
                action, checked, AUTOSTART_FILE, autostart=True
            )
        )
        sys_menu.addAction(autostart_action)
        
        sys_menu.addSeparator()
        
        kwin_menu = sys_menu.addMenu("KWin helper")
        kwin_available = _is_kde_session() and _resolve_kwin_tools() is not None

        kwin_hint_action = QAction("Fix Layer/Persistence via KDE Rule", self)
        kwin_hint_action.setCheckable(True)
        enabled = is_kwin_rule_enabled()
        kwin_hint_action.setChecked(enabled)
        kwin_hint_action.triggered.connect(
            lambda checked, action=kwin_hint_action: self._toggle_kwin_rule(action, checked)
        )
        sys_menu.addAction(kwin_hint_action)

        reload_kwin_action = QAction("Reload KWin rules", self)
        reload_kwin_action.setEnabled(kwin_available)
        reload_kwin_action.triggered.connect(self._reload_kwin_rules_with_feedback)
        kwin_menu.addAction(reload_kwin_action)

        if not kwin_available:
            kwin_hint_action = QAction("Unavailable outside KDE/KWin", self)
            kwin_hint_action.setEnabled(False)
            kwin_menu.addAction(kwin_hint_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        menu.exec_(event.globalPos())

    def _toggle_entry(self, action: QAction, checked: bool, path: Path, autostart: bool) -> None:
        # For launchers/autostart, we omit explicit settings flags so the app loads the latest saved state.
        ok = set_desktop_entry_enabled(
            path, checked, self._runtime_launch_command(include_settings=False), autostart=autostart
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
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self.drag_offset is None or not (event.buttons() & Qt.LeftButton):
            return

        if not self.drag_started and self.press_global_pos is not None:
            drag_distance = (event.globalPos() - self.press_global_pos).manhattanLength()
            if drag_distance > self.click_threshold_px:
                self.drag_started = True
                
                # FORCE HANDOVER: On Wayland, this is the only way to move.
                window_handle = self.windowHandle()
                if window_handle is not None:
                    print(">>> MOUSE: Attempting system move handover...")
                    if hasattr(window_handle, "startSystemMove"):
                        if window_handle.startSystemMove():
                            print(">>> MOUSE: System took over dragging.")
                            self.drag_offset = None 
                            self.drag_started = True
                            event.accept()
                            return
                    else:
                        print(">>> MOUSE: windowHandle has no startSystemMove!")

        if self.drag_started and self.drag_offset is not None:
            self.move(event.globalPos() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if event.button() != Qt.LeftButton:
            return

        was_click = False
        if self.press_global_pos is not None:
            distance = (event.globalPos() - self.press_global_pos).manhattanLength()
            was_click = distance <= self.click_threshold_px and not self.drag_started

        if self.stopwatch_active and was_click:
            self.toggle_stopwatch_running()

        if self.drag_started:
            # On Wayland, startSystemMove hides the final position until 
            # the system finishes processing the move. We wait 500ms to 
            # polling the final coordinates from the Window Manager.
            QTimer.singleShot(500, self.save_state)

        self.drag_offset = None
        self.press_global_pos = None
        self.drag_started = False
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt signature)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = THEME_PRESETS[_valid_theme(self.color_theme)]

        # Digital Mode uses a horizontal "pill" shape if width > height
        if self.mode == MODE_DIGITAL:
            face_bounds = QRectF(6, 6, self.width() - 12, self.height() - 12)
        else:
            face_bounds = QRectF(6, 6, self.clock_size - 12, self.clock_size - 12)
            
        center = face_bounds.center()
        radius = min(face_bounds.width(), face_bounds.height()) / 2

        # Draw Face with Gradient (uses face_alpha)
        gradient = QLinearGradient(face_bounds.topLeft(), face_bounds.bottomRight())
        fill_colors = palette["face_fill"]
        gradient.setColorAt(0, _qcolor(fill_colors[0], self.face_alpha))
        gradient.setColorAt(1, _qcolor(fill_colors[1], self.face_alpha))

        border_alpha = min(self.face_alpha * 1.5, 1.0) # Keep border slightly more visible
        border_color = _qcolor(palette["face_border"], border_alpha)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(QBrush(gradient))
        
        if self.mode == MODE_DIGITAL:
            # Draw pill shape
            corner_radius = radius
            painter.drawRoundedRect(face_bounds, corner_radius, corner_radius)
        else:
            painter.drawEllipse(face_bounds)

        # Glass Highlight (uses face_alpha)
        highlight_center = center - QPointF(radius * 0.3, radius * 0.3)
        glass_grad = QRadialGradient(highlight_center, radius * 1.2)
        highlight_color = _qcolor(palette["glass_highlight"], self.face_alpha)
        glass_grad.setColorAt(0, highlight_color)
        glass_grad.setColorAt(1, Qt.transparent)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(glass_grad)
        if self.mode == MODE_DIGITAL:
            painter.drawRoundedRect(face_bounds, corner_radius, corner_radius)
        else:
            painter.drawEllipse(face_bounds)

        # NOTE: Foreground elements (tick marks, hands, etc.) 
        # do NOT use alpha_scale inside their draw methods below, 
        # making them independent of face_alpha.

        if self.stopwatch_active:
            if self.mode == MODE_ANALOG:
                self._draw_stopwatch_tick_marks(painter, center, radius, palette)
                self._draw_stopwatch_hands(painter, center, radius, palette)
                self._draw_stopwatch_readout(painter, palette)
            else: # MODE_DIGITAL
                self._draw_digital_stopwatch(painter, center, radius, palette)
        else:
            if self.mode == MODE_DIGITAL:
                self._draw_digital_time(painter, center, radius, palette)
            else:
                self._draw_clock_tick_marks(painter, center, radius, palette)
                self._draw_clock_hands(painter, center, radius, palette)

        # Draw Center Dot (Analog only)
        if self.mode == MODE_ANALOG and not self.stopwatch_active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(_qcolor(palette["center_dot"]))
            painter.drawEllipse(center, radius * 0.04, radius * 0.04)

        painter.end()

    def _format_digital_time(self) -> str:
        now = datetime.now()
        fmt = "%H:%M:%S" if self.show_seconds else "%H:%M"
        return now.strftime(fmt)

    def _draw_digital_stopwatch(self, painter: QPainter, center: QPointF, radius: float, palette: dict) -> None:
        ms = self._current_stopwatch_ms()
        raw_text = self._format_stopwatch_elapsed(ms)
        self._draw_centered_text(painter, center, radius, palette, raw_text, "STOPWATCH")

    def _draw_digital_time(self, painter: QPainter, center: QPointF, radius: float, palette: dict) -> None:
        raw_text = self._format_digital_time()
        self._draw_centered_text(painter, center, radius, palette, raw_text, "")

    def _draw_centered_text(self, painter: QPainter, center: QPointF, radius: float, palette: dict, raw_text: str, label: str) -> None:
        # Start with a base font size and scale down if it exceeds the face bounds
        font_size = radius * 0.7 
        font = QFont(self.readout_font_family)
        font.setBold(True)
        
        # Iterative scale down to fit the text comfortably
        max_content_width = (self.width() - 32)
        while font_size > 10:
            font.setPointSizeF(font_size)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            rect = metrics.boundingRect(raw_text)
            if rect.width() < max_content_width:
                break
            font_size -= 2

        metrics = painter.fontMetrics()
        rect = metrics.boundingRect(raw_text)
        
        # Center the text vertically and horizontally
        text_rect = QRectF(
            center.x() - rect.width() / 2,
            center.y() - rect.height() / 2,
            rect.width(),
            rect.height()
        )
        
        painter.setPen(_qcolor(palette["text_primary"]))
        painter.drawText(text_rect, Qt.AlignCenter, raw_text)

        # Draw small label below if space permits
        if radius > 60:
            label_font = QFont(self.readout_font_family)
            label_font.setPointSizeF(radius * 0.12)
            label_font.setWeight(QFont.DemiBold)
            label_font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
            painter.setFont(label_font)
            
            label_rect = QRectF(center.x() - radius, center.y() + radius * 0.45, radius * 2, radius * 0.2)
            painter.setPen(_qcolor(palette["text_secondary"]))
            painter.drawText(label_rect, Qt.AlignCenter, label)

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
            self.readout_height_actual - 14,
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
        
        # Subtle hand shadow
        shadow_offset = QPointF(1.5, 1.5)
        shadow_pen = QPen(QColor(0, 0, 0, 70), width)
        shadow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(shadow_pen)
        painter.drawLine(center + shadow_offset, endpoint + shadow_offset)

        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(center, endpoint)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Floating analog clock and stopwatch widget.",
        argument_default=argparse.SUPPRESS
    )
    # Arguments are added below with SUPPRESS defaults
    parser.add_argument(
        "--size",
        type=int,
        help=f"Clock size in pixels ({MIN_CLOCK_SIZE}-{MAX_CLOCK_SIZE}).",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        help="Clock face opacity between 0.05 and 0.95.",
    )
    parser.add_argument(
        "--hide-seconds",
        action="store_true",
        default=None,
        help="Hide the seconds hand in analog mode.",
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_ANALOG, MODE_DIGITAL, "clock", "stopwatch"],
        help="Launch mode (analog or digital). Legacy 'clock' and 'stopwatch' also supported.",
    )
    parser.add_argument(
        "--stopwatch",
        action="store_true",
        default=None,
        help="Enable stopwatch mode on launch.",
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
    parser.add_argument(
        "--force-cli",
        "-f",
        action="store_true",
        help="FORCE the use of CLI arguments over saved state (bypasses Smart-Supreme logic).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Emergency Reset: Kills other instances and deletes saved state.",
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

    # Safety: Handle suppressed arguments with default False for validation
    inst_menu = getattr(args, "install_menu_entry", False)
    uninst_menu = getattr(args, "uninstall_menu_entry", False)
    inst_auto = getattr(args, "install_autostart", False)
    uninst_auto = getattr(args, "uninstall_autostart", False)
    inst_kwin = getattr(args, "install_kwin_rule", False)
    uninst_kwin = getattr(args, "uninstall_kwin_rule", False)

    if inst_menu and uninst_menu:
        parser.error("Choose only one of --install-menu-entry or --uninstall-menu-entry.")
    if inst_auto and uninst_auto:
        parser.error("Choose only one of --install-autostart or --uninstall-autostart.")
    if inst_kwin and uninst_kwin:
        parser.error("Choose only one of --install-kwin-rule or --uninstall-kwin-rule.")
    return args


def main() -> int:
    args = parse_args()
    _log(f"Main entry. CMD: {' '.join(sys.argv)}")
    
    if getattr(args, "reset", False):
        _log("EMERGENCY RESET INITIATED")
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print("Reset complete. Saved state deleted. Relaunching in 1s...")
        time.sleep(1)
        # Note: We don't pkill here to avoid suicide before return, 
        # but the lock check below will handle it or user can restart.

    saved_state = load_saved_state()
    force_cli = getattr(args, "force_cli", False)

    def _resolve_smart(key: str, cli_val: any, state_val: any, default: any) -> any:
        if force_cli:
            return cli_val if cli_val is not None else (state_val if state_val is not None else default)
        
        # GHOST SIGNATURE (The stock defaults being injected by hidden scripts)
        GHOST_SIG = {
            "size": 220,
            "opacity": 0.45,
            "mode": "clock",
            "theme": "high_contrast",
            "layer": LAYER_BOTTOM,
            "readout_font": "Noto Color Emoji"
        }
        
        if state_val is not None and cli_val is not None:
            # If CLI is the GHOST, trust the Saved State
            if key in GHOST_SIG and cli_val == GHOST_SIG[key]:
                _log(f"SMART-SUPREME: Blocked Ghost '{key}={cli_val}' (Using State '{state_val}')")
                return state_val
            
            # If CLI is DIFFERENT from ghost, it's a User Override!
            _log(f"SMART-SUPREME: User override detected '{key}={cli_val}' (Will update state)")
            return cli_val

        return cli_val if cli_val is not None else (state_val if state_val is not None else default)

    # 1. RESOLVE CORE VALUES (Smart-Supreme applied)
    raw_size = _resolve_smart("size", getattr(args, "size", None), saved_state.get("size"), DEFAULT_CLOCK_SIZE)
    raw_mode = _resolve_smart("mode", getattr(args, "mode", None), saved_state.get("mode"), DEFAULT_MODE)
    raw_layer = _resolve_smart("layer", getattr(args, "layer", None), saved_state.get("layer"), DEFAULT_LAYER)
    raw_theme = _resolve_smart("theme", getattr(args, "theme", None), saved_state.get("theme"), DEFAULT_THEME)
    raw_font = _resolve_smart("readout_font", getattr(args, "readout_font", None), saved_state.get("readout_font"), DEFAULT_READOUT_FONT)
    
    # 2. RESOLVE COMPLEX VALUES
    cli_opacity = getattr(args, "opacity", None)
    launch_opacity = _resolve_smart("opacity", cli_opacity, saved_state.get("opacity"), 0.45)
    
    # VISIBILITY GUARD: If layer is normal and opacity is too low, boost it for start
    if raw_layer == LAYER_NORMAL and launch_opacity < 0.25:
        _log(f"VISIBILITY GUARD: Boosting opacity from {launch_opacity:.2f} to 0.35 for launch.")
        launch_opacity = 0.35

    saved_show_seconds = saved_state.get("show_seconds")
    cli_hide_seconds = getattr(args, "hide_seconds", None)
    
    if not force_cli and saved_show_seconds is not None:
        launch_show_seconds = bool(saved_show_seconds)
    else:
        launch_show_seconds = False if cli_hide_seconds is True else (bool(saved_show_seconds) if saved_show_seconds is not None else True)
        
    cli_stopwatch = getattr(args, "stopwatch", None)
    launch_stopwatch = (
        cli_stopwatch is True or 
        raw_mode == "stopwatch" or 
        bool(saved_state.get("stopwatch_active", False))
    )
    if cli_stopwatch is False:
        launch_stopwatch = False

    # 3. VALIDATE AND NORMALIZE
    launch_size = _valid_size(raw_size)
    launch_mode = _valid_mode(raw_mode)
    launch_layer = _valid_layer(raw_layer)
    launch_theme = _valid_theme(raw_theme)
    launch_font = _normalize_readout_font(raw_font)
    
    initial_stopwatch_running = bool(saved_state.get("stopwatch_running", False))
    initial_stopwatch_elapsed = int(saved_state.get("stopwatch_elapsed", 0))

    # 4. DIAGNOSTICS (VERY IMPORTANT FOR THE USER)
    print(f">>> STARTUP: Merged configuration...")
    print(f"    Mode: {launch_mode}, Size: {launch_size}, Layer: {launch_layer}")
    print(f"    Opacity: {launch_opacity:.2f}, Seconds: {launch_show_seconds}, Stopwatch: {launch_stopwatch}")
    print(f"    State Path: {STATE_FILE}")

    # 5. PREPARE LAUNCHER COMMAND (BARE - NO SETTINGS TO OVERRIDE STATE)
    launch_command = build_launch_command(
        size=launch_size,
        opacity=launch_opacity,
        hide_seconds=not launch_show_seconds,
        layer=launch_layer,
        mode=launch_mode,
        theme=launch_theme,
        readout_font=launch_font,
        include_settings=False,
    )
    
    install_exit = handle_install_flags(args, launch_command)
    if install_exit is not None:
        return install_exit
        
    # AUTO-REPAIR: If launchers exist, refresh them to remove hardcoded flags
    if MENU_ENTRY_FILE.exists():
        write_desktop_entry(MENU_ENTRY_FILE, launch_command, autostart=False)
    if AUTOSTART_FILE.exists():
        write_desktop_entry(AUTOSTART_FILE, launch_command, autostart=True)
        
    if PYQT_IMPORT_ERROR is not None:
        print("PyQt5 is required to run the clock UI. Install with: sudo pacman -S python-pyqt5")
        return 1

    # SINGLE INSTANCE LOCK
    lock_file = STATE_DIR / "instance.lock"
    if lock_file.exists():
        try:
            old_pid = int(lock_file.read_text().strip())
            os.kill(old_pid, 0) # Check if process exists
            print(f"!!! Clock is already running (PID {old_pid}). Exiting.")
            return 0
        except (OSError, ValueError):
            pass # Stale lock
    lock_file.write_text(str(os.getpid()))

    app = QApplication([])
    app.setDesktopFileName(APP_ID)
    app.setApplicationName(APP_NAME)

    clock = FloatingAnalogClock(
        size=launch_size,
        face_alpha=launch_opacity,
        show_seconds=launch_show_seconds,
        layer=launch_layer,
        mode=launch_mode,
        stopwatch_active=launch_stopwatch,
        color_theme=launch_theme,
        readout_font=launch_font,
        initial_x=int(saved_state.get("x", 0)),
        initial_y=int(saved_state.get("y", 0)),
    )
    
    _log("Clock instance created with initial geometry.")
    
    # Restore stopwatch time and status
    clock.stopwatch_elapsed_ms = initial_stopwatch_elapsed
    if initial_stopwatch_running and launch_stopwatch:
        clock.toggle_stopwatch_running()
    
    # Crucial: Apply flags, apply size, Move, then Show.
    clock._set_window_flags(launch_layer)
    clock._apply_window_size()
    clock.show()
    
    # HEAVY-DUTY WAYLAND DELAYED PLACEMENT
    def delayed_restore():
        # Wayland ignores the first few move() attempts while surface maps.
        # We hit it with a sequence of increasing delays.
        clock.restore_position(getattr(args, "x", None), getattr(args, "y", None), saved_state)
        # Final layering re-assertion via system rules
        if _is_kde_session() and is_kwin_rule_enabled():
            clock.set_layer(launch_layer, persist=False, force=True)

    # Multi-tap restoration to ensure Wayland compositor registers the position
    QTimer.singleShot(500, delayed_restore)
    QTimer.singleShot(1200, delayed_restore)
    QTimer.singleShot(2500, delayed_restore)
    
    # Definitive initialization lock: 10 seconds for Wayland stabilization
    QTimer.singleShot(10000, lambda: setattr(clock, 'fully_initialized', True))
    _log("Startup sequence complete. 10s initialization lock active.")

    try:
        exit_code = app.exec_()
    finally:
        try:
            lock_file.unlink()
        except OSError:
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
