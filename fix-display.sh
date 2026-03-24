#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Walkman PiTFT Fix Script
#  Fixes: display output going to wrong screen + touch input
# ──────────────────────────────────────────────────────────────

echo ""
echo "  Walkman PiTFT Display Fix"
echo "──────────────────────────────────────────────────────────────"
echo ""

USER_HOME="/home/mp4"

# ── Step 1: Create xorg config dir ───────────────────────────
echo "→ Setting up display config..."
sudo mkdir -p /etc/X11/xorg.conf.d

# ── Step 2: Write xorg config ────────────────────────────────
# Points X at /dev/fb1 (PiTFT) and sets up touch input
sudo tee /etc/X11/xorg.conf.d/99-pitft.conf > /dev/null << 'EOF'
Section "Device"
    Identifier "PiTFT"
    Driver "fbdev"
    Option "fbdev" "/dev/fb1"
EndSection

Section "Screen"
    Identifier "PiTFT Screen"
    Device "PiTFT"
EndSection

Section "InputClass"
    Identifier "PiTFT Touch"
    MatchProduct "ft6x06_ts"
    Option "SwapAxes" "0"
    Option "InvertY" "0"
EndSection
EOF

echo "✓ Display config written"

# ── Step 3: Fix the crontab ───────────────────────────────────
echo "→ Fixing crontab autostart..."

# Remove old walkman crontab entry and write a clean one
( crontab -l 2>/dev/null | grep -v walkman; echo "@reboot sleep 12 && DISPLAY=:0 xinit $USER_HOME/.local/bin/walkman -- :0 vt1 2>/tmp/walkman.log" ) | crontab -

echo "✓ Crontab updated"

# ── Step 4: Make sure xinit and fbdev driver are installed ────
echo "→ Checking xinit and fbdev driver..."
sudo apt install -y xinit xserver-xorg-video-fbdev xserver-xorg-input-evdev 2>/dev/null

echo "✓ Display packages ready"

# ── Step 5: Fix the walkman launcher just in case ─────────────
echo "→ Checking walkman launcher..."
if [ -f "$USER_HOME/.local/bin/walkman" ]; then
    # Make sure it has the right display export
    cat > "$USER_HOME/.local/bin/walkman" << EOF2
#!/bin/bash
export DISPLAY=:0
cd $USER_HOME/.local/share/walkman
python3 $USER_HOME/.local/share/walkman/walkman.py "\$@"
EOF2
    chmod +x "$USER_HOME/.local/bin/walkman"
    echo "✓ Launcher updated"
else
    echo "✗ Walkman launcher not found — did the install.sh complete?"
    exit 1
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────────────────────────"
echo "  ✓ All done! Rebooting in 5 seconds..."
echo "  (The app should appear on the PiTFT screen after boot)"
echo "──────────────────────────────────────────────────────────────"
echo ""
sleep 5
sudo reboot
