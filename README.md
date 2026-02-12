# DT Clock

Floating analog desktop clock for CachyOS/Linux using PyQt5.

## Features

- Frameless, translucent analog clock
- Drag to move anywhere
- Built-in stopwatch mode with face click start/stop
- Millisecond digital readout below the face in stopwatch mode
- Readout font selection from installed monospaced fonts
- In-app clock size controls for different screen resolutions
- Window layer controls (`Always on top`, `Normal`, `Below windows`)
- Optional KDE/KWin keep-above rule helper
- Multiple color themes for light/dark/high-contrast desktops
- Right-click menu with `Preferences`
- Toggle `Show in apps menu` from the clock itself
- Toggle `Start at login` from the clock itself
- Remembers last position
- Optional seconds hand
- `--on-top`, `--normal-layer`, or `--on-bottom` window hint

## Install

On Arch/CachyOS:

```bash
sudo pacman -S python-pyqt5
```

## Run

From this project directory:

```bash
python3 floating_clock.py
```

Useful options:

```bash
python3 floating_clock.py --size 260 --opacity 0.35
python3 floating_clock.py --hide-seconds
python3 floating_clock.py --on-bottom
python3 floating_clock.py --normal-layer
python3 floating_clock.py --install-kwin-rule
python3 floating_clock.py --mode stopwatch
python3 floating_clock.py --theme daylight
python3 floating_clock.py --mode stopwatch --readout-font "JetBrains Mono"
python3 floating_clock.py --x 120 --y 80
```

## Stopwatch Mode

1. Right-click clock -> `Mode` -> `Stopwatch`
2. Left-click the clock face to start or stop timing
3. Right-click -> `Reset stopwatch` to clear elapsed time

The stopwatch readout shows millisecond precision and appears below the clock face.

## App Menu Launcher

Install a user-level launcher so the clock appears in your desktop app menu:

```bash
python3 floating_clock.py --install-menu-entry
```

Remove it:

```bash
python3 floating_clock.py --uninstall-menu-entry
```

The launcher is written to:

```text
~/.local/share/applications/dt-clock.desktop
```

Keep the project in a permanent location before installing menu/autostart entries, because the launcher stores the absolute path to `floating_clock.py`.

## Autostart

Enable autostart:

```bash
python3 floating_clock.py --install-autostart
```

Disable autostart:

```bash
python3 floating_clock.py --uninstall-autostart
```

The autostart entry is written to:

```text
~/.config/autostart/dt-clock.desktop
```

## KDE/KWin Helper

For KDE Plasma users, install a KWin rule that reinforces keep-above behavior:

```bash
python3 floating_clock.py --install-kwin-rule
```

Remove it:

```bash
python3 floating_clock.py --uninstall-kwin-rule
```

This helper updates:

```text
~/.config/kwinrulesrc
```

## In-App Preferences

While the clock is running, right-click it:

- `Mode` -> `Clock` or `Stopwatch`
- `Preferences` -> `Window layer` (`Always on top`, `Normal`, `Below windows`)
- `Preferences` -> `KWin helper` (`Enable keep-above rule`, `Reload KWin rules`)
- `Preferences` -> `Clock size` (`Smaller`, `Larger`, plus presets)
- `Preferences` -> `Color theme` (`Midnight`, `Daylight`, `High Contrast`, `Ocean`)
- `Preferences` -> `Show in apps menu`
- `Preferences` -> `Start at login`
- `Preferences` -> `Readout font`

The readout font menu is populated from fonts installed on your system, so changes should apply immediately.

`Center on screen` centers the widget on the monitor where the clock currently is (or the cursor monitor if needed).

## Wayland Note

- On X11, position/drag behavior is usually unrestricted.
- On Wayland, compositor rules may limit exact placement and some window-layer hints (`--on-top` / `--on-bottom`) may be ignored.
- On KDE/Wayland, enabling `Preferences -> KWin helper -> Enable keep-above rule` usually improves consistency.
- This script attempts a compositor-native move request first (`startSystemMove`) for better Wayland behavior.
