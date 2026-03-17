# 🎵 Walkman — Raspberry Pi Music & Video Player

A sleek, Sony Walkman-inspired media player for Raspberry Pi running Linux.  
Plays music and music videos with a beautiful dark retro-modern UI.

---

## Features

- **Music Playback** — MP3, FLAC, WAV, OGG, AAC, M4A, OPUS, WMA
- **Video Playback** — MP4, MKV, AVI, MOV, WEBM, and more (opens fullscreen)
- **Animated Visualizer** — Real-time bar visualizer while music plays
- **Retro Dark UI** — Orange-on-black Sony Walkman aesthetic
- **Live Search** — Instantly filter your library as you type
- **Transport Controls** — Play, Pause, Prev, Next with progress bar
- **Shuffle & Repeat** — Shuffle, Repeat All, or Repeat One
- **Volume Control** — On-screen slider
- **Filter Tabs** — Show All / Music only / Video only
- **Persistent Config** — Remembers your folders, volume, and settings
- **Fullscreen** — Press F11 to go fullscreen (great for Pi touchscreens)

---

## Requirements

- Raspberry Pi running Raspberry Pi OS (or any Debian-based Linux)
- Python 3.7+
- `python3-tk` — for the GUI
- `mpv` — audio/video playback backend

---

## Installation

```bash
# 1. Clone or copy this folder to your Pi, then:
cd walkman
chmod +x install.sh
./install.sh
```

This installs all dependencies, copies the app, and creates a desktop shortcut.

---

## Running

```bash
# From terminal:
walkman

# Or double-click "Walkman" in the Applications → Sound & Video menu
```

---

## Usage

1. Click **＋ Add Folder** to add your music/video directory (e.g. `~/Music`)
2. Browse your library in the left panel
3. **Double-click** a track to play it
4. Use transport buttons to skip, pause, seek
5. Toggle **Shuffle** (⇀) and **Repeat** (↺/↻) modes
6. Filter by All / Music / Video using the top-right tabs
7. Search by typing in the search box

---

## Keyboard Shortcuts

| Key       | Action              |
|-----------|---------------------|
| `F11`     | Toggle fullscreen   |
| `Escape`  | Exit fullscreen     |

---

## File Structure

```
walkman/
├── walkman.py      # Main application
├── install.sh      # Installer script
└── README.md       # This file
```

Config is saved to `~/.walkman_config.json`

---

## Tips for Raspberry Pi

- For **touchscreen** use, run fullscreen with `F11` after launching
- For **autostart on boot**, add `walkman` to your desktop autostart file:
  ```
  ~/.config/autostart/walkman.desktop
  ```
  Copy the `.desktop` file from `~/.local/share/applications/walkman.desktop`

- For **headless audio** (no monitor), mpv handles audio-only tracks automatically

---

## Architecture

- **UI**: Python `tkinter` — lightweight, no extra GUI dependencies
- **Backend**: `mpv` via subprocess + Unix IPC socket for real-time control
- **Visualizer**: Pure tkinter Canvas with animated bars (simulated, since raw PCM 
  access requires additional libraries — add `librosa` for real FFT analysis)

---

## License

MIT — free to use, modify, and distribute.
