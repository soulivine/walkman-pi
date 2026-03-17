# 🎵 Walkman — PiTFT Edition

**Raspberry Pi Zero 2 W + Adafruit PiTFT Plus 2.8" 320×240 Capacitive Touchscreen**

A Sony Walkman-inspired music & video player purpose-built for the tiny PiTFT screen with physical button support and Bluetooth headphone pairing.

---

## Hardware

| Component | Part |
|-----------|------|
| Computer | Raspberry Pi Zero 2 W |
| Display | Adafruit PiTFT Plus 2.8" (#1983) |
| Resolution | 320 × 240 |
| Touch | Capacitive (finger touch) |
| Buttons | 4 physical side buttons |
| Audio | Bluetooth headphones |

---

## Physical Button Layout

```
┌─────────────────┐
│                 │ ← BTN 1 (GPIO 17) = Play / Pause
│                 │
│   [  screen  ]  │ ← BTN 2 (GPIO 22) = Previous Track
│                 │
│                 │ ← BTN 3 (GPIO 23) = Next Track
│                 │
│                 │ ← BTN 4 (GPIO 27) = Mute / Unmute
└─────────────────┘
```

---

## Screens

### Player (main screen)
- Album art / track type icon
- Track title
- Animated bar visualizer
- Touchable seek bar
- ▶ / ⏸ / ⏮ / ⏭ transport controls
- Shuffle and Repeat toggles
- Touchable volume slider
- Bluetooth connection status in top bar
- Nav bar → Library / Settings / Bluetooth

### Library
- Searchable track list
- Filter: All / Music / Video
- Tap once, then tap again to play (touch-friendly)

### Bluetooth
- Scan for nearby devices (8 second scan)
- Connect / Disconnect with one tap
- Shows currently connected device

### Settings
- Add/remove music folders
- Screen brightness slider
- Rescan library
- Shutdown / Restart buttons

---

## Installation

### Step 0 — Set up PiTFT display first
Run Adafruit's official installer:
```bash
curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/adafruit-pitft.py | sudo python3
```
Select **PiTFT 2.8" capacitive (#1983)**, then reboot.

### Step 1 — Clone and install Walkman
```bash
git clone https://github.com/YOUR_USERNAME/walkman-pi.git
cd walkman-pi
chmod +x install.sh
./install.sh
```

### Step 2 — Add music
```bash
# Copy music to the default folder:
cp -r /path/to/music ~/Music/

# Or use a USB drive — mount it and add the folder in Settings
```

### Step 3 — Launch
```bash
walkman
```

---

## Pairing Bluetooth Headphones

1. Put your headphones in **pairing mode**
2. In Walkman, tap **🔵 BLUETOOTH** (bottom nav)
3. Tap **🔍 SCAN FOR DEVICES** (waits ~8 seconds)
4. Tap your headphones in the list
5. Tap **⚡ CONNECT**

Once paired, the headphones will auto-reconnect on future boots if you run:
```bash
bluetoothctl trust YOUR_MAC_ADDRESS
```
(The app does this automatically when you connect.)

---

## Autostart on Boot

The installer offers to enable autostart. To do it manually:
```bash
mkdir -p ~/.config/autostart
cp ~/.local/share/applications/walkman.desktop ~/.config/autostart/
```

---

## Supported Formats

**Music:** MP3, FLAC, WAV, OGG, AAC, M4A, OPUS, WMA  
**Video:** MP4, MKV, AVI, MOV, WEBM, M4V, FLV, MPG  
(Videos play fullscreen via mpv)

---

## Requirements

Installed automatically by `install.sh`:
- `python3` + `python3-tk`
- `mpv` — media playback backend
- `python3-rpi.gpio` — physical button support
- `bluez` + `pulseaudio-module-bluetooth` — Bluetooth audio

---

## File Structure

```
walkman-pi/
├── walkman.py     # Full application (~600 lines)
├── install.sh     # Installer
└── README.md      # This file
```

Config saved to: `~/.walkman_config.json`

---

## Tips

- **No cursor** shown (hidden for touchscreen cleanliness)
- **Escape key** exits the app (useful during development)
- **Arrow keys** work for playback control when testing on a desktop
- The app runs **fullscreen** at 320×240 automatically
- Add multiple music folders from the Settings screen
- USB drives work — mount them and add the path in Settings
