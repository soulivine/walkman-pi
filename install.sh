#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Walkman Player — Raspberry Pi Installer
# ─────────────────────────────────────────────────────────────

set -e

echo ""
echo "  ██╗    ██╗ █████╗ ██╗     ██╗  ██╗███╗   ███╗ █████╗ ███╗  ██╗"
echo "  ██║    ██║██╔══██╗██║     ██║ ██╔╝████╗ ████║██╔══██╗████╗ ██║"
echo "  ██║ █╗ ██║███████║██║     █████╔╝ ██╔████╔██║███████║██╔██╗██║"
echo "  ██║███╗██║██╔══██║██║     ██╔═██╗ ██║╚██╔╝██║██╔══██║██║╚████║"
echo "  ╚███╔███╔╝██║  ██║███████╗██║  ██╗██║ ╚═╝ ██║██║  ██║██║ ╚███║"
echo "   ╚══╝╚══╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚══╝"
echo ""
echo "  Raspberry Pi Music & Video Player Installer"
echo "────────────────────────────────────────────────────────────────────"
echo ""

# Check we're on a Debian/Ubuntu-based system
if ! command -v apt &> /dev/null; then
    echo "⚠  This installer is for Debian/Raspbian-based systems."
    echo "   Please install dependencies manually: python3, python3-tk, mpv"
    exit 1
fi

echo "→ Updating package lists..."
sudo apt update -qq

echo "→ Installing Python 3 and tkinter..."
sudo apt install -y python3 python3-tk python3-pip

echo "→ Installing mpv (audio/video player backend)..."
sudo apt install -y mpv

echo "→ Installing optional fonts..."
sudo apt install -y fonts-dejavu fonts-dejavu-extra 2>/dev/null || true

echo ""
echo "→ Installing Walkman player..."
INSTALL_DIR="$HOME/.local/share/walkman"
mkdir -p "$INSTALL_DIR"
cp walkman.py "$INSTALL_DIR/walkman.py"
chmod +x "$INSTALL_DIR/walkman.py"

# Create launcher script
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/walkman" << 'EOF'
#!/bin/bash
python3 "$HOME/.local/share/walkman/walkman.py" "$@"
EOF
chmod +x "$HOME/.local/bin/walkman"

# Create desktop entry
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/walkman.desktop" << EOF
[Desktop Entry]
Name=Walkman
Comment=Music & Video Player
Exec=$HOME/.local/bin/walkman
Icon=multimedia-player
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Video;Player;
Keywords=music;video;player;walkman;
EOF

echo ""
echo "────────────────────────────────────────────────────────────────────"
echo "  ✓ Installation complete!"
echo ""
echo "  Run Walkman:   walkman"
echo "                 (or from the Applications menu → Sound & Video)"
echo ""
echo "  Keyboard shortcuts inside the player:"
echo "    F11      — Toggle fullscreen"
echo "    Escape   — Exit fullscreen"
echo ""
echo "  Tip: Add your ~/Music folder using the '＋ Add Folder' button."
echo "────────────────────────────────────────────────────────────────────"
