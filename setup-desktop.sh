#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Walkman — Lightweight Desktop Fix
#  Replaces full desktop with openbox (bare minimum window manager)
#  and autostart walkman on boot
# ──────────────────────────────────────────────────────────────

echo ""
echo "  Walkman Lightweight Desktop Setup"
echo "──────────────────────────────────────────────────────────────"
echo ""

# ── Install openbox ───────────────────────────────────────────
echo "→ Installing openbox..."
sudo apt install -y openbox

# ── Set openbox as default session ───────────────────────────
echo "→ Setting openbox as default window manager..."
sudo update-alternatives --set x-session-manager /usr/bin/openbox-session 2>/dev/null || true

# ── Autostart walkman in openbox ─────────────────────────────
echo "→ Setting up walkman autostart..."
mkdir -p /home/mp4/.config/openbox
cat > /home/mp4/.config/openbox/autostart << 'EOF'
# Hide cursor
unclutter -idle 0 &

# Launch Walkman
python3 /home/mp4/walkman-pi/walkman.py &
EOF

# ── Install unclutter to hide mouse cursor ────────────────────
echo "→ Installing unclutter (hides cursor on touchscreen)..."
sudo apt install -y unclutter

# ── Set boot to desktop autologin ────────────────────────────
echo "→ Setting boot to desktop autologin..."
sudo raspi-config nonint do_boot_behaviour B4

# ── Clean up any old autostart attempts ──────────────────────
echo "→ Cleaning up old autostart files..."
rm -f /home/mp4/.config/autostart/walkman.desktop
# Clear bash_profile
echo "" > /home/mp4/.bash_profile
# Clear crontab
crontab -r 2>/dev/null || true

echo ""
echo "──────────────────────────────────────────────────────────────"
echo "  ✓ Done! Rebooting in 5 seconds..."
echo "  Walkman will launch automatically with no desktop"
echo "──────────────────────────────────────────────────────────────"
echo ""
sleep 5
sudo reboot
