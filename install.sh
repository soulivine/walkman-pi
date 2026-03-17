#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Walkman PiTFT Installer
#  For: Raspberry Pi Zero 2 W + Adafruit PiTFT Plus 2.8" 320x240
# ──────────────────────────────────────────────────────────────

set -e

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
CYN='\033[0;36m'; BLD='\033[1m'; RST='\033[0m'

echo ""
echo -e "${CYN}${BLD}  ██╗    ██╗ █████╗ ██╗     ██╗  ██╗███╗   ███╗ █████╗ ███╗  ██╗${RST}"
echo -e "${CYN}${BLD}  ██║ █╗ ██║██╔══██╗██║     ██╔ ██╔╝████╗ ████║██╔══██╗████╗ ██║${RST}"
echo -e "${CYN}${BLD}  ╚███╔███╔╝██║  ██║███████╗██║  ██╗██║ ╚═╝ ██║██║  ██║██║ ╚███║${RST}"
echo ""
echo -e "  ${BLD}PiTFT Edition — Raspberry Pi Zero 2 W${RST}"
echo "  Adafruit 2.8\" 320×240 Capacitive Touchscreen"
echo "──────────────────────────────────────────────────────────────"
echo ""

# ── Check system ──────────────────────────────────────────────
if ! command -v apt &>/dev/null; then
    echo -e "${RED}✗ This installer requires a Debian/Raspbian-based OS.${RST}"
    exit 1
fi

echo -e "${GRN}→ Updating package list...${RST}"
sudo apt update -qq

# ── Core packages ─────────────────────────────────────────────
echo -e "${GRN}→ Installing Python 3 + tkinter...${RST}"
sudo apt install -y python3 python3-tk python3-pip

echo -e "${GRN}→ Installing mpv (media backend)...${RST}"
sudo apt install -y mpv

echo -e "${GRN}→ Installing RPi.GPIO for physical buttons...${RST}"
sudo apt install -y python3-rpi.gpio

echo -e "${GRN}→ Installing Bluetooth tools...${RST}"
sudo apt install -y bluez bluez-tools pulseaudio pulseaudio-module-bluetooth

echo -e "${GRN}→ Installing fonts...${RST}"
sudo apt install -y fonts-dejavu fonts-dejavu-extra 2>/dev/null || true

# ── PiTFT display setup ───────────────────────────────────────
echo ""
echo -e "${YLW}── PiTFT Display Setup ──────────────────────────────────────${RST}"
echo ""

# Check if PiTFT overlay is already configured
if grep -q "dtoverlay=pitft28-capacitive" /boot/config.txt 2>/dev/null || \
   grep -q "dtoverlay=pitft28-capacitive" /boot/firmware/config.txt 2>/dev/null; then
    echo -e "${GRN}✓ PiTFT overlay already configured.${RST}"
else
    echo -e "${YLW}⚠  PiTFT display overlay not detected in config.txt${RST}"
    echo ""
    echo "  To set up the PiTFT display, run Adafruit's installer:"
    echo -e "  ${BLD}curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/adafruit-pitft.py | sudo python3${RST}"
    echo ""
    echo "  Select: PiTFT 2.8\" capacitive (product #1983)"
    echo "  Then reboot and re-run this installer."
    echo ""
    read -p "  Continue anyway? (y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0
fi

# ── Bluetooth audio setup ─────────────────────────────────────
echo ""
echo -e "${GRN}→ Configuring Bluetooth audio...${RST}"

# Enable bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth || true

# Add user to bluetooth group
sudo usermod -aG bluetooth "$USER" || true

# Configure PulseAudio for Bluetooth
PULSE_CONF="$HOME/.config/pulse/default.pa"
mkdir -p "$HOME/.config/pulse"

if ! grep -q "module-bluetooth-policy" "$PULSE_CONF" 2>/dev/null; then
    cat >> "$PULSE_CONF" << 'EOF'

# Bluetooth audio
load-module module-bluetooth-policy
load-module module-bluetooth-discover
EOF
    echo -e "${GRN}✓ PulseAudio Bluetooth modules configured.${RST}"
fi

# ── Install walkman ───────────────────────────────────────────
echo ""
echo -e "${GRN}→ Installing Walkman...${RST}"

INSTALL_DIR="$HOME/.local/share/walkman"
mkdir -p "$INSTALL_DIR"
cp walkman.py "$INSTALL_DIR/walkman.py"
chmod +x "$INSTALL_DIR/walkman.py"

mkdir -p "$HOME/Music"

# Launcher
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/walkman" << EOF
#!/bin/bash
# Ensure DISPLAY is set for PiTFT
export DISPLAY=:0
cd "$INSTALL_DIR"
python3 walkman.py "\$@"
EOF
chmod +x "$HOME/.local/bin/walkman"

# Desktop entry
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/walkman.desktop" << EOF
[Desktop Entry]
Name=Walkman
Comment=Music & Video Player
Exec=$HOME/.local/bin/walkman
Icon=multimedia-player
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Video;
EOF

# ── Autostart ─────────────────────────────────────────────────
echo ""
read -p "  Auto-start Walkman on boot? (Y/n): " autostart
if [[ ! "$autostart" =~ ^[Nn]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    cat > "$HOME/.config/autostart/walkman.desktop" << EOF
[Desktop Entry]
Name=Walkman
Exec=$HOME/.local/bin/walkman
Type=Application
EOF
    echo -e "${GRN}✓ Autostart enabled.${RST}"
fi

# ── Button permissions ────────────────────────────────────────
# Allow GPIO without sudo
if ! groups "$USER" | grep -q gpio; then
    sudo usermod -aG gpio "$USER" 2>/dev/null || true
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${GRN}──────────────────────────────────────────────────────────────${RST}"
echo -e "${GRN}${BLD}  ✓ Installation complete!${RST}"
echo ""
echo "  Run:      walkman"
echo "  Or:       python3 ~/.local/share/walkman/walkman.py"
echo ""
echo -e "${YLW}  Physical button layout (PiTFT side buttons):${RST}"
echo "    Button 1 (top)    → Play / Pause"
echo "    Button 2          → Previous track"
echo "    Button 3          → Next track"
echo "    Button 4 (bottom) → Mute / Unmute"
echo ""
echo -e "${YLW}  First run steps:${RST}"
echo "    1. Drop music into ~/Music"
echo "    2. Launch walkman"
echo "    3. Tap SETTINGS → rescan to find tracks"
echo "    4. Tap BLUETOOTH to pair headphones"
echo -e "${GRN}──────────────────────────────────────────────────────────────${RST}"
echo ""

# Suggest reboot if groups changed
echo -e "${YLW}⚠  A reboot is recommended to apply Bluetooth + GPIO group changes.${RST}"
read -p "  Reboot now? (y/N): " reboot_now
[[ "$reboot_now" =~ ^[Yy]$ ]] && sudo reboot
