# DT Clock 🕰️

[![Support on Ko-fi](https://img.shields.io/badge/Support-Ko--fi-F16061?style=flat-square&logo=ko-fi&logoColor=white)](https://ko-fi.com/pyrategfxproductions)

**A sleek, customizable, and minimalist floating analog clock for your desktop.**

DT Clock is a highly versatile desktop widget designed for both **Linux (CachyOS/Arch/KDE)** and **Windows**. It combines a classic analog aesthetic with modern features like transparency, window layering, and a built-in precision stopwatch.

---

## ✨ Key Features

- **🖼️ Frameless & Translucent:** A clean, minimalist design that blends into any desktop wallpaper.
- **🖱️ Fully Interactive:** Drag to position anywhere; right-click for a comprehensive preferences menu.
- **⏱️ Integrated Stopwatch:**
  - Start/stop with a simple click on the clock face.
  - High-precision millisecond digital readout.
  - Custom font selection for the digital display.
- **🎨 Visual Customization:**
  - **Themes:** Choose from Midnight, Daylight, High Contrast, and Ocean.
  - **Sizing:** Real-time scaling to fit your screen resolution.
  - **Second Hand:** Optional toggle for a cleaner look.
- **🪟 Window Management:**
  - **Layer Control:** Set to "Always on Top," "Normal," or "Below Windows."
  - **KDE Integration:** Specialized KWin rule helper for Linux users to ensure consistent "Keep Above" behavior.
- **⚙️ Desktop Integration:**
  - **Autostart:** Toggle "Start at login" directly from the app.
  - **App Menu:** Automatically creates/removes desktop launcher entries.
  - **State Persistence:** Remembers your position, size, and theme across restarts.

---

## 🚀 Installation & Setup

### For Windows Users
The easiest way to use DT Clock on Windows is to download the latest executable from the [Releases](https://github.com/PyrateGFXProductions/DT_Clock/releases) page.

**To run from source:**
1. Ensure you have [Python 3](https://www.python.org/downloads/) installed.
2. Install dependencies:
   ```bash
   pip install PyQt5
   ```
3. Launch the app:
   ```bash
   python floating_clock.py
   ```

### For Linux Users (Arch/CachyOS)
1. Install PyQt5:
   ```bash
   sudo pacman -S python-pyqt5
   ```
2. Launch the app:
   ```bash
   python3 floating_clock.py
   ```

---

## 🛠️ Advanced Usage (Command Line)

You can launch DT Clock with specific parameters to bypass saved settings:

```bash
# Set specific size and opacity
python3 floating_clock.py --size 300 --opacity 0.8

# Launch directly in stopwatch mode with a custom font
python3 floating_clock.py --mode stopwatch --readout-font "JetBrains Mono"

# Force window layer behavior
python3 floating_clock.py --on-top    # Always stay on top
python3 floating_clock.py --on-bottom # Act as wallpaper/below windows
```

---

## 📦 Releases & Binaries

**Note for Users:** You do not need to install Python or compile code to use DT Clock.
1. Navigate to the **[Releases](https://github.com/PyrateGFXProductions/DT_Clock/releases)** section on GitHub.
2. Download the latest `DT_Clock.exe` (Windows) or the appropriate Linux binary.
3. Simply run the file to start the clock!

**Note for Developers:** 
Binaries are excluded from this repository to keep the source control lean. If you wish to build your own binary, you can use PyInstaller:
```bash
pyinstaller --onefile --windowed --name "DT Clock" --clean floating_clock.py
```

---

## ☕ Support the Project

If you find DT Clock useful and would like to support its development, consider buying me a coffee! Your support helps keep the project alive and free for everyone.

[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20Me%20a%20Coffee-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/pyrategfxproductions)

---

## 📄 License

This project is open-source. Feel free to fork, modify, and share!

---
*Developed with ❤️ for the desktop customization community.*
