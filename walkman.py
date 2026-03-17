#!/usr/bin/env python3
"""
Walkman Player — PiTFT 320×240 Edition
Optimized for Adafruit PiTFT Plus 2.8" Capacitive Touchscreen
Pi Zero 2 W | 4 Physical Buttons | Bluetooth Headphone Support
"""

import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import os
import json
import time
import random
from pathlib import Path

# ─── Display Constants ────────────────────────────────────────────────────────

SCREEN_W = 320
SCREEN_H = 240

MUSIC_EXTS = {'.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.opus', '.wma'}
VIDEO_EXTS  = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv', '.mpg'}

CONFIG_FILE = Path.home() / '.walkman_config.json'

# PiTFT GPIO button pin mapping (BCM)
# Physical button positions on the 2.8" PiTFT Plus:
#   BTN1 = GPIO17  (top)
#   BTN2 = GPIO22
#   BTN3 = GPIO23
#   BTN4 = GPIO27  (bottom)
GPIO_BTNS = [17, 22, 23, 27]

# ─── Colors ───────────────────────────────────────────────────────────────────

C = {
    'bg':       '#080810',
    'surface':  '#10101C',
    'surface2': '#18182A',
    'surface3': '#222235',
    'border':   '#2C2C45',
    'accent':   '#FF6B35',
    'accent2':  '#FFAA00',
    'adim':     '#5C2510',
    'text':     '#EEEEFF',
    'dim':      '#7777AA',
    'mute':     '#333355',
    'green':    '#44EE88',
    'blue':     '#55AAFF',
    'red':      '#FF4455',
}

# ─── Config ───────────────────────────────────────────────────────────────────

def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except:
        pass
    return {
        'music_dirs': [str(Path.home() / 'Music')],
        'volume': 85,
        'shuffle': False,
        'repeat': 'none',
    }

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except:
        pass

# ─── File Scanner ─────────────────────────────────────────────────────────────

def scan_dirs(dirs):
    tracks = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, subdirs, files in os.walk(d):
            subdirs.sort()
            for f in sorted(files):
                ext = Path(f).suffix.lower()
                if ext in MUSIC_EXTS | VIDEO_EXTS:
                    tracks.append({
                        'path': os.path.join(root, f),
                        'name': Path(f).stem,
                        'ext':  ext,
                        'type': 'video' if ext in VIDEO_EXTS else 'music',
                    })
    return tracks

# ─── MPV Backend ──────────────────────────────────────────────────────────────

class Player:
    def __init__(self):
        self.proc    = None
        self.ipc     = '/tmp/wm_mpv.sock'
        self.volume  = 85
        self.playing = False
        self.paused  = False
        self._pos    = 0.0
        self._dur    = 0.0
        self._live   = False
        self.on_end  = None
        self.on_tick = None

    def _ipc(self, cmd):
        try:
            import socket, json as j
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.4)
            s.connect(self.ipc)
            s.send((j.dumps(cmd) + '\n').encode())
            time.sleep(0.04)
            try:
                raw = s.recv(4096).decode()
                s.close()
                for line in raw.strip().split('\n'):
                    try:
                        obj = j.loads(line)
                        if obj.get('error') == 'success':
                            return obj.get('data')
                    except:
                        pass
            except:
                s.close()
        except:
            pass
        return None

    def play(self, path, video=False):
        self.stop()
        self.playing = True
        self.paused  = False
        self._pos    = 0.0
        self._dur    = 0.0

        cmd = ['mpv', f'--input-ipc-server={self.ipc}',
               f'--volume={self.volume}', '--no-terminal']
        if not video:
            cmd += ['--no-video', '--audio-display=no']
        else:
            cmd += ['--fs', '--no-keepaspect-window']
        cmd.append(path)

        try:
            self.proc = subprocess.Popen(cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            self.playing = False
            return False

        self._live = True
        threading.Thread(target=self._monitor, daemon=True).start()
        return True

    def _monitor(self):
        time.sleep(0.8)
        while self._live and self.proc and self.proc.poll() is None:
            pos = self._ipc({"command": ["get_property", "time-pos"]})
            dur = self._ipc({"command": ["get_property", "duration"]})
            if pos is not None: self._pos = float(pos)
            if dur is not None: self._dur = float(dur)
            if self.on_tick:
                self.on_tick(self._pos, self._dur)
            time.sleep(0.5)
        if self._live:
            self.playing = False
            self.paused  = False
            if self.on_end:
                self.on_end()
        self._live = False

    def pause(self):
        self._ipc({"command": ["cycle", "pause"]})
        self.paused = not self.paused

    def stop(self):
        self._live = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except:
                try: self.proc.kill()
                except: pass
        self.proc    = None
        self.playing = False
        self.paused  = False
        self._pos    = 0.0
        self._dur    = 0.0

    def seek(self, secs):
        self._ipc({"command": ["seek", secs, "absolute"]})

    def set_volume(self, v):
        self.volume = max(0, min(100, int(v)))
        self._ipc({"command": ["set_property", "volume", self.volume]})

    @property
    def pos(self): return self._pos
    @property
    def dur(self): return self._dur

# ─── Bluetooth Manager ────────────────────────────────────────────────────────

class BluetoothManager:
    def scan(self, duration=8):
        """Run bluetoothctl scan, return list of (mac, name) tuples."""
        devices = {}
        try:
            proc = subprocess.Popen(
                ['bluetoothctl'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            proc.stdin.write('scan on\n')
            proc.stdin.flush()
            time.sleep(duration)
            proc.stdin.write('scan off\n')
            proc.stdin.flush()
            time.sleep(0.5)
            proc.stdin.write('devices\n')
            proc.stdin.flush()
            time.sleep(0.5)
            proc.stdin.write('quit\n')
            proc.stdin.flush()
            out, _ = proc.communicate(timeout=5)
            for line in out.split('\n'):
                if 'Device' in line:
                    parts = line.strip().split(' ', 2)
                    if len(parts) >= 3:
                        mac  = parts[1]
                        name = parts[2] if len(parts) > 2 else mac
                        devices[mac] = name
        except Exception as e:
            pass
        return list(devices.items())

    def connect(self, mac):
        """Pair, trust, and connect to a device."""
        cmds = f'pair {mac}\ntrust {mac}\nconnect {mac}\nquit\n'
        try:
            result = subprocess.run(
                ['bluetoothctl'],
                input=cmds, capture_output=True, text=True, timeout=20
            )
            return 'Connected' in result.stdout or 'successful' in result.stdout.lower()
        except:
            return False

    def disconnect(self, mac):
        try:
            subprocess.run(['bluetoothctl', 'disconnect', mac],
                           capture_output=True, timeout=10)
            return True
        except:
            return False

    def paired_devices(self):
        try:
            out = subprocess.check_output(
                ['bluetoothctl', 'paired-devices'], text=True, timeout=5)
            devs = []
            for line in out.strip().split('\n'):
                parts = line.split(' ', 2)
                if len(parts) >= 2 and len(parts[1]) == 17:
                    devs.append((parts[1], parts[2] if len(parts) > 2 else parts[1]))
            return devs
        except:
            return []

    def connected_device(self):
        try:
            for mac, name in self.paired_devices():
                out = subprocess.check_output(
                    ['bluetoothctl', 'info', mac], text=True, timeout=5)
                if 'Connected: yes' in out:
                    return mac, name
        except:
            pass
        return None, None

# ─── UI Helpers ───────────────────────────────────────────────────────────────

def fmt_time(s):
    s = int(s)
    m, s = divmod(s, 60)
    return f'{m}:{s:02d}'

def make_btn(parent, text, cmd, font_size=11, width=None, height=None,
             fg=None, bg=None, active_fg=None):
    kw = dict(
        text=text, command=cmd,
        font=('DejaVu Sans', font_size, 'bold'),
        fg=fg or C['text'],
        bg=bg or C['surface2'],
        activeforeground=active_fg or C['accent2'],
        activebackground=bg or C['surface2'],
        relief='flat', bd=0,
        cursor='hand2',
        highlightthickness=1,
        highlightbackground=C['border'],
    )
    if width:  kw['width'] = width
    if height: kw['height'] = height
    return tk.Button(parent, **kw)

# ─── Views ────────────────────────────────────────────────────────────────────

class PlayerView(tk.Frame):
    """Main playback screen — fits 320×240."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=C['bg'])
        self.app = app
        self._seek_drag = False
        self._build()

    def _build(self):
        # ── Top status bar (16px) ──
        status = tk.Frame(self, bg=C['surface'], height=16)
        status.pack(fill='x')
        status.pack_propagate(False)

        self.bt_label = tk.Label(status, text='BT', font=('DejaVu Sans Mono', 7),
                                  fg=C['mute'], bg=C['surface'])
        self.bt_label.pack(side='left', padx=4)

        self.vol_label = tk.Label(status, text='VOL 85%',
                                   font=('DejaVu Sans Mono', 7),
                                   fg=C['dim'], bg=C['surface'])
        self.vol_label.pack(side='right', padx=4)

        self.mode_label = tk.Label(status, text='',
                                    font=('DejaVu Sans Mono', 7),
                                    fg=C['accent'], bg=C['surface'])
        self.mode_label.pack(side='right', padx=2)

        # ── Art + info row (80px) ──
        mid = tk.Frame(self, bg=C['bg'])
        mid.pack(fill='x', padx=4, pady=(3, 0))

        # Art square 72×72
        self.art = tk.Canvas(mid, width=72, height=72,
                              bg=C['surface2'], highlightthickness=1,
                              highlightbackground=C['border'])
        self.art.pack(side='left', padx=(2, 6))
        self._draw_art(None)

        # Info column
        info = tk.Frame(mid, bg=C['bg'])
        info.pack(side='left', fill='both', expand=True)

        self.title_var = tk.StringVar(value='No track')
        self.title_lbl = tk.Label(info, textvariable=self.title_var,
                                   font=('DejaVu Sans', 9, 'bold'),
                                   fg=C['text'], bg=C['bg'],
                                   anchor='w', wraplength=220, justify='left')
        self.title_lbl.pack(fill='x')

        self.type_lbl = tk.Label(info, text='—',
                                  font=('DejaVu Sans Mono', 7),
                                  fg=C['accent'], bg=C['bg'], anchor='w')
        self.type_lbl.pack(fill='x')

        # Visualizer — 30px tall
        self.vis = VisualizerBar(info, height=30)
        self.vis.pack(fill='x', pady=(4, 0))

        # ── Seek bar row (20px) ──
        seek_row = tk.Frame(self, bg=C['bg'])
        seek_row.pack(fill='x', padx=4, pady=(4, 0))

        self.t_left = tk.Label(seek_row, text='0:00',
                                font=('DejaVu Sans Mono', 7),
                                fg=C['dim'], bg=C['bg'], width=4)
        self.t_left.pack(side='left')

        self.seek_cv = tk.Canvas(seek_row, height=14, bg=C['bg'],
                                  highlightthickness=0, cursor='hand2')
        self.seek_cv.pack(side='left', fill='x', expand=True, padx=3)
        self.seek_cv.bind('<ButtonPress-1>',   self._seek_press)
        self.seek_cv.bind('<B1-Motion>',       self._seek_drag_cb)
        self.seek_cv.bind('<ButtonRelease-1>', self._seek_release)
        self._seek_pct = 0.0

        self.t_right = tk.Label(seek_row, text='0:00',
                                 font=('DejaVu Sans Mono', 7),
                                 fg=C['dim'], bg=C['bg'], width=4)
        self.t_right.pack(side='left')

        # ── Transport controls (44px) ──
        transport = tk.Frame(self, bg=C['surface'], height=44)
        transport.pack(fill='x', pady=(4, 0))
        transport.pack_propagate(False)

        btn_kw = dict(font=('DejaVu Sans', 13), relief='flat', bd=0,
                      bg=C['surface'], activebackground=C['surface'],
                      cursor='hand2', width=3)

        self.shuf_btn = tk.Button(transport, text='⇀',
                                   fg=C['accent'] if self.app.shuffle else C['mute'],
                                   command=self.app.toggle_shuffle, **btn_kw)
        self.shuf_btn.pack(side='left', padx=2)

        tk.Button(transport, text='⏮', fg=C['dim'],
                  activeforeground=C['accent'],
                  command=self.app.prev_track, **btn_kw).pack(side='left')

        self.play_btn = tk.Button(transport, text='▶',
                                   font=('DejaVu Sans', 16, 'bold'),
                                   fg=C['accent'], bg=C['adim'],
                                   activebackground=C['adim'],
                                   activeforeground=C['accent2'],
                                   relief='flat', bd=0, cursor='hand2', width=3,
                                   command=self.app.toggle_play)
        self.play_btn.pack(side='left', padx=4)

        tk.Button(transport, text='⏭', fg=C['dim'],
                  activeforeground=C['accent'],
                  command=self.app.next_track, **btn_kw).pack(side='left')

        self.rep_btn = tk.Button(transport, text='↺',
                                  fg=C['mute'],
                                  command=self.app.cycle_repeat, **btn_kw)
        self.rep_btn.pack(side='left', padx=2)

        # ── Volume bar (20px) ──
        vol_row = tk.Frame(self, bg=C['bg'])
        vol_row.pack(fill='x', padx=6, pady=(3, 0))

        tk.Label(vol_row, text='🔈', font=('DejaVu Sans', 8),
                 fg=C['mute'], bg=C['bg']).pack(side='left')

        self.vol_cv = tk.Canvas(vol_row, height=12, bg=C['bg'],
                                 highlightthickness=0, cursor='hand2')
        self.vol_cv.pack(side='left', fill='x', expand=True, padx=3)
        self.vol_cv.bind('<ButtonPress-1>',   self._vol_press)
        self.vol_cv.bind('<B1-Motion>',       self._vol_drag)
        self.vol_cv.bind('<ButtonRelease-1>', self._vol_release)

        tk.Label(vol_row, text='🔊', font=('DejaVu Sans', 8),
                 fg=C['dim'], bg=C['bg']).pack(side='left')

        # ── Bottom nav bar (28px) ──
        nav = tk.Frame(self, bg=C['surface2'], height=28)
        nav.pack(fill='x', side='bottom')
        nav.pack_propagate(False)

        nav_kw = dict(font=('DejaVu Sans', 8), relief='flat', bd=0,
                      bg=C['surface2'], activebackground=C['surface3'],
                      cursor='hand2', pady=0)

        tk.Button(nav, text='♪ LIBRARY', fg=C['accent'],
                  activeforeground=C['accent2'],
                  command=lambda: self.app.show_view('library'),
                  **nav_kw).pack(side='left', expand=True, fill='both')

        tk.Frame(nav, bg=C['border'], width=1).pack(side='left', fill='y')

        tk.Button(nav, text='⚙ SETTINGS', fg=C['dim'],
                  activeforeground=C['text'],
                  command=lambda: self.app.show_view('settings'),
                  **nav_kw).pack(side='left', expand=True, fill='both')

        tk.Frame(nav, bg=C['border'], width=1).pack(side='left', fill='y')

        tk.Button(nav, text='🔵 BLUETOOTH', fg=C['dim'],
                  activeforeground=C['blue'],
                  command=lambda: self.app.show_view('bluetooth'),
                  **nav_kw).pack(side='left', expand=True, fill='both')

        self._draw_seek(0)
        self._draw_vol(self.app.config.get('volume', 85))

    # ── Art ──
    def _draw_art(self, track):
        self.art.delete('all')
        self.art.create_rectangle(0, 0, 72, 72, fill=C['surface2'], outline='')
        if track is None:
            self.art.create_oval(18, 18, 54, 54, outline=C['border'], width=2)
            self.art.create_oval(28, 28, 44, 44, fill=C['surface3'], outline=C['border'])
            self.art.create_oval(33, 33, 39, 39, fill=C['adim'], outline='')
        elif track['type'] == 'video':
            self.art.create_rectangle(8, 18, 64, 54, fill=C['surface3'], outline=C['border'])
            self.art.create_polygon(26, 26, 26, 46, 52, 36, fill=C['accent'], outline='')
        else:
            self.art.create_oval(10, 10, 62, 62, outline=C['adim'], width=2)
            self.art.create_oval(22, 22, 50, 50, outline=C['adim'], width=1)
            self.art.create_oval(30, 30, 42, 42, fill=C['surface3'], outline=C['accent'], width=2)
            self.art.create_oval(34, 34, 38, 38, fill=C['accent'], outline='')

    # ── Seek bar ──
    def _draw_seek(self, pct):
        self._seek_pct = max(0.0, min(1.0, pct))
        self.seek_cv.delete('all')
        w = self.seek_cv.winfo_width() or 180
        h = 14
        # Track
        self.seek_cv.create_rectangle(0, 5, w, 9, fill=C['surface3'], outline='')
        # Fill
        fw = int(w * self._seek_pct)
        if fw > 0:
            self.seek_cv.create_rectangle(0, 5, fw, 9, fill=C['accent'], outline='')
        # Thumb
        tx = max(6, min(w - 6, fw))
        self.seek_cv.create_oval(tx-5, 2, tx+5, 12, fill=C['accent2'], outline='')

    def _seek_press(self, e):
        self._seek_drag = True
        self._seek_move(e.x)

    def _seek_drag_cb(self, e):
        if self._seek_drag:
            self._seek_move(e.x)

    def _seek_move(self, x):
        w = self.seek_cv.winfo_width() or 180
        pct = max(0, min(1, x / w))
        self._draw_seek(pct)

    def _seek_release(self, e):
        self._seek_drag = False
        w = self.seek_cv.winfo_width() or 180
        pct = max(0, min(1, e.x / w))
        self.app.seek_to(pct)

    # ── Volume bar ──
    def _draw_vol(self, pct_int):
        pct = pct_int / 100
        self.vol_cv.delete('all')
        w = self.vol_cv.winfo_width() or 160
        self.vol_cv.create_rectangle(0, 4, w, 8, fill=C['surface3'], outline='')
        fw = int(w * pct)
        if fw > 0:
            self.vol_cv.create_rectangle(0, 4, fw, 8, fill=C['accent2'], outline='')
        tx = max(5, min(w - 5, fw))
        self.vol_cv.create_oval(tx-4, 2, tx+4, 10, fill=C['accent2'], outline='')

    def _vol_press(self, e):
        self._set_vol(e.x)

    def _vol_drag(self, e):
        self._set_vol(e.x)

    def _vol_release(self, e):
        self._set_vol(e.x)

    def _set_vol(self, x):
        w = self.vol_cv.winfo_width() or 160
        pct = max(0, min(100, int((x / w) * 100)))
        self._draw_vol(pct)
        self.app.set_volume(pct)

    # ── Update from app ──
    def update_track(self, track):
        self._draw_art(track)
        if track:
            name = track['name']
            if len(name) > 28: name = name[:26] + '…'
            self.title_var.set(name)
            self.type_lbl.config(text='▶ VIDEO' if track['type'] == 'video' else '♪ AUDIO')
        else:
            self.title_var.set('No track')
            self.type_lbl.config(text='—')

    def update_position(self, pos, dur):
        if not self._seek_drag:
            pct = (pos / dur) if dur > 0 else 0
            self._draw_seek(pct)
        self.t_left.config(text=fmt_time(pos))
        self.t_right.config(text=fmt_time(dur))

    def update_play_state(self, playing, paused):
        self.play_btn.config(text='⏸' if (playing and not paused) else '▶')
        self.vis.set_playing(playing and not paused)

    def update_shuffle(self, on):
        self.shuf_btn.config(fg=C['accent'] if on else C['mute'])

    def update_repeat(self, mode):
        sym = {'none': '↺', 'all': '↺', 'one': '↻'}[mode]
        col = {'none': C['mute'], 'all': C['accent'], 'one': C['accent2']}[mode]
        self.rep_btn.config(text=sym, fg=col)

    def update_volume(self, v):
        self.vol_label.config(text=f'VOL {v}%')
        self._draw_vol(v)

    def update_bt(self, name):
        if name:
            short = name[:12] + '…' if len(name) > 12 else name
            self.bt_label.config(text=f'🔵{short}', fg=C['blue'])
        else:
            self.bt_label.config(text='BT', fg=C['mute'])

    def update_mode(self, shuffle, repeat):
        parts = []
        if shuffle: parts.append('SHF')
        if repeat != 'none': parts.append('RPT' if repeat == 'all' else 'R:1')
        self.mode_label.config(text=' '.join(parts))


class LibraryView(tk.Frame):
    """Scrollable track list — finger-friendly rows."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=C['bg'])
        self.app = app
        self._tracks = []
        self._filtered = []
        self._build()

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg=C['surface'], height=24)
        top.pack(fill='x')
        top.pack_propagate(False)

        tk.Button(top, text='◀', font=('DejaVu Sans', 10), fg=C['accent'],
                  bg=C['surface'], activebackground=C['surface'],
                  relief='flat', bd=0, cursor='hand2',
                  command=lambda: self.app.show_view('player')).pack(side='left', padx=6)

        tk.Label(top, text='LIBRARY', font=('DejaVu Sans Mono', 8, 'bold'),
                 fg=C['text'], bg=C['surface']).pack(side='left')

        self.count_lbl = tk.Label(top, text='', font=('DejaVu Sans Mono', 7),
                                   fg=C['dim'], bg=C['surface'])
        self.count_lbl.pack(side='right', padx=6)

        # Search
        search_f = tk.Frame(self, bg=C['surface2'], height=24)
        search_f.pack(fill='x')
        search_f.pack_propagate(False)

        tk.Label(search_f, text='⌕', font=('DejaVu Sans', 10),
                 fg=C['dim'], bg=C['surface2']).pack(side='left', padx=4)

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._filter)
        tk.Entry(search_f, textvariable=self.search_var,
                 font=('DejaVu Sans', 9), fg=C['text'], bg=C['surface3'],
                 insertbackground=C['accent'], relief='flat', bd=0
                 ).pack(fill='x', expand=True, padx=4, ipady=2)

        # Filter tabs
        tabs = tk.Frame(self, bg=C['surface3'])
        tabs.pack(fill='x')
        self.filter_var = tk.StringVar(value='all')
        for lbl, val in [('All', 'all'), ('Music', 'music'), ('Video', 'video')]:
            tk.Radiobutton(tabs, text=lbl, variable=self.filter_var, value=val,
                           font=('DejaVu Sans', 8), fg=C['dim'],
                           selectcolor=C['surface3'], bg=C['surface3'],
                           activebackground=C['surface3'],
                           activeforeground=C['accent'],
                           indicatoron=False, relief='flat', bd=0,
                           padx=8, pady=3, cursor='hand2',
                           command=self._filter).pack(side='left', expand=True)

        # Track listbox with scrollbar
        list_f = tk.Frame(self, bg=C['bg'])
        list_f.pack(fill='both', expand=True)

        sb = tk.Scrollbar(list_f, bg=C['surface3'], troughcolor=C['bg'],
                          relief='flat', bd=0, width=6)
        sb.pack(side='right', fill='y')

        self.lb = tk.Listbox(list_f, font=('DejaVu Sans', 9),
                              fg=C['dim'], bg=C['bg'],
                              selectbackground=C['adim'],
                              selectforeground=C['accent2'],
                              activestyle='none',
                              relief='flat', bd=0, highlightthickness=0,
                              yscrollcommand=sb.set, cursor='hand2')
        self.lb.pack(fill='both', expand=True)
        sb.config(command=self.lb.yview)
        self.lb.bind('<Double-Button-1>', self._select)
        self.lb.bind('<ButtonRelease-1>', self._single_tap)

        self._tap_time = 0
        self._tap_idx  = -1

    def _single_tap(self, e):
        # On small touchscreen, single tap = play (double-tap is hard)
        idx = self.lb.nearest(e.y)
        now = time.time()
        if idx == self._tap_idx and (now - self._tap_time) < 0.6:
            self._do_select(idx)
        self._tap_time = now
        self._tap_idx  = idx

    def _select(self, e=None):
        sel = self.lb.curselection()
        if sel:
            self._do_select(sel[0])

    def _do_select(self, pos):
        if pos < len(self._filtered):
            track = self._filtered[pos]
            real_idx = self.app.tracks.index(track)
            self.app.play_index(real_idx)
            self.app.show_view('player')

    def set_tracks(self, tracks):
        self._tracks = tracks
        self._filter()

    def _filter(self, *_):
        q   = self.search_var.get().lower()
        flt = self.filter_var.get()
        self._filtered = [
            t for t in self._tracks
            if (flt == 'all' or t['type'] == flt)
            and (not q or q in t['name'].lower())
        ]
        self.lb.delete(0, 'end')
        for t in self._filtered:
            icon = '▶' if t['type'] == 'video' else '♪'
            self.lb.insert('end', f' {icon} {t["name"]}')
        self.count_lbl.config(text=f'{len(self._filtered)} tracks')

    def highlight(self, index):
        if 0 <= index < len(self.app.tracks):
            track = self.app.tracks[index]
            if track in self._filtered:
                pos = self._filtered.index(track)
                self.lb.selection_clear(0, 'end')
                self.lb.selection_set(pos)
                self.lb.see(pos)


class BluetoothView(tk.Frame):
    """Bluetooth headphone pairing screen."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=C['bg'])
        self.app = app
        self.bt  = BluetoothManager()
        self._scanning = False
        self._devices  = []
        self._build()

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg=C['surface'], height=24)
        top.pack(fill='x')
        top.pack_propagate(False)

        tk.Button(top, text='◀', font=('DejaVu Sans', 10), fg=C['accent'],
                  bg=C['surface'], activebackground=C['surface'],
                  relief='flat', bd=0, cursor='hand2',
                  command=lambda: self.app.show_view('player')).pack(side='left', padx=6)

        tk.Label(top, text='BLUETOOTH', font=('DejaVu Sans Mono', 8, 'bold'),
                 fg=C['blue'], bg=C['surface']).pack(side='left')

        # Connected device banner
        self.conn_lbl = tk.Label(self, text='Not connected',
                                  font=('DejaVu Sans', 8),
                                  fg=C['dim'], bg=C['surface2'], pady=4)
        self.conn_lbl.pack(fill='x')

        # Scan button + status
        ctrl = tk.Frame(self, bg=C['bg'])
        ctrl.pack(fill='x', padx=6, pady=4)

        self.scan_btn = make_btn(ctrl, '🔍 SCAN FOR DEVICES', self._start_scan,
                                  font_size=9, fg=C['blue'], bg=C['surface2'])
        self.scan_btn.pack(side='left', fill='x', expand=True, ipady=6)

        self.status_lbl = tk.Label(ctrl, text='', font=('DejaVu Sans', 7),
                                    fg=C['accent'], bg=C['bg'], width=8)
        self.status_lbl.pack(side='left', padx=4)

        # Device list
        list_f = tk.Frame(self, bg=C['bg'])
        list_f.pack(fill='both', expand=True, padx=4)

        tk.Label(list_f, text='AVAILABLE DEVICES',
                 font=('DejaVu Sans Mono', 7), fg=C['mute'], bg=C['bg'],
                 anchor='w').pack(fill='x', pady=(2, 0))

        sb = tk.Scrollbar(list_f, bg=C['surface3'], troughcolor=C['bg'],
                          relief='flat', bd=0, width=6)
        sb.pack(side='right', fill='y')

        self.lb = tk.Listbox(list_f, font=('DejaVu Sans', 9),
                              fg=C['text'], bg=C['surface2'],
                              selectbackground=C['adim'],
                              selectforeground=C['blue'],
                              activestyle='none', relief='flat', bd=0,
                              highlightthickness=0, yscrollcommand=sb.set,
                              cursor='hand2')
        self.lb.pack(fill='both', expand=True)
        sb.config(command=self.lb.yview)

        # Connect / Disconnect buttons
        btn_row = tk.Frame(self, bg=C['bg'])
        btn_row.pack(fill='x', padx=4, pady=4)

        make_btn(btn_row, '⚡ CONNECT', self._connect,
                 font_size=9, fg=C['green'], bg=C['surface2']
                 ).pack(side='left', fill='x', expand=True, padx=(0, 2), ipady=5)

        make_btn(btn_row, '✕ DISCONNECT', self._disconnect,
                 font_size=9, fg=C['red'], bg=C['surface2']
                 ).pack(side='left', fill='x', expand=True, padx=(2, 0), ipady=5)

        self._refresh_connected()

    def on_show(self):
        self._refresh_connected()
        self._load_paired()

    def _refresh_connected(self):
        mac, name = self.bt.connected_device()
        if name:
            self.conn_lbl.config(
                text=f'🔵 Connected: {name}', fg=C['blue'])
            self.app.player_view.update_bt(name)
        else:
            self.conn_lbl.config(text='Not connected', fg=C['dim'])
            self.app.player_view.update_bt(None)

    def _load_paired(self):
        self.lb.delete(0, 'end')
        self._devices = self.bt.paired_devices()
        for mac, name in self._devices:
            self.lb.insert('end', f' 🔵 {name}')

    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self.scan_btn.config(state='disabled', text='Scanning…')
        self.status_lbl.config(text='…8s')
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        found = self.bt.scan(duration=8)
        # Merge with paired
        paired = self.bt.paired_devices()
        all_macs = {m for m, _ in self._devices}
        for mac, name in found:
            if mac not in all_macs:
                self._devices.append((mac, name))
        self.after(0, self._scan_done)

    def _scan_done(self):
        self._scanning = False
        self.scan_btn.config(state='normal', text='🔍 SCAN FOR DEVICES')
        self.status_lbl.config(text='Done')
        self.lb.delete(0, 'end')
        for mac, name in self._devices:
            self.lb.insert('end', f' 📶 {name}')
        self.after(2000, lambda: self.status_lbl.config(text=''))

    def _connect(self):
        sel = self.lb.curselection()
        if not sel or sel[0] >= len(self._devices):
            return
        mac, name = self._devices[sel[0]]
        self.status_lbl.config(text='…')
        self.scan_btn.config(state='disabled')

        def do():
            ok = self.bt.connect(mac)
            self.after(0, lambda: self._connect_done(ok, name))

        threading.Thread(target=do, daemon=True).start()

    def _connect_done(self, ok, name):
        self.scan_btn.config(state='normal')
        if ok:
            self.conn_lbl.config(text=f'🔵 Connected: {name}', fg=C['blue'])
            self.app.player_view.update_bt(name)
            self.status_lbl.config(text='✓')
        else:
            self.status_lbl.config(text='✗ Fail')
        self.after(2000, lambda: self.status_lbl.config(text=''))

    def _disconnect(self):
        mac, name = self.bt.connected_device()
        if mac:
            self.bt.disconnect(mac)
            self._refresh_connected()


class SettingsView(tk.Frame):
    """Settings: music dirs, display brightness, shutdown."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=C['bg'])
        self.app = app
        self._build()

    def _build(self):
        top = tk.Frame(self, bg=C['surface'], height=24)
        top.pack(fill='x')
        top.pack_propagate(False)

        tk.Button(top, text='◀', font=('DejaVu Sans', 10), fg=C['accent'],
                  bg=C['surface'], activebackground=C['surface'],
                  relief='flat', bd=0, cursor='hand2',
                  command=lambda: self.app.show_view('player')).pack(side='left', padx=6)

        tk.Label(top, text='SETTINGS', font=('DejaVu Sans Mono', 8, 'bold'),
                 fg=C['text'], bg=C['surface']).pack(side='left')

        # Music directories
        tk.Label(self, text='MUSIC FOLDERS', font=('DejaVu Sans Mono', 7),
                 fg=C['mute'], bg=C['bg'], anchor='w'
                 ).pack(fill='x', padx=6, pady=(6, 0))

        dir_f = tk.Frame(self, bg=C['surface2'])
        dir_f.pack(fill='x', padx=6)

        self.dir_lb = tk.Listbox(dir_f, font=('DejaVu Sans', 8),
                                  fg=C['dim'], bg=C['surface2'],
                                  selectbackground=C['adim'],
                                  activestyle='none', relief='flat', bd=0,
                                  highlightthickness=0, height=3)
        self.dir_lb.pack(fill='x', expand=True, side='left')

        dir_btns = tk.Frame(dir_f, bg=C['surface2'])
        dir_btns.pack(side='right', fill='y')
        make_btn(dir_btns, '+', self._add_dir, font_size=10,
                 fg=C['green'], bg=C['surface3']
                 ).pack(fill='x', pady=1, ipady=4, padx=2)
        make_btn(dir_btns, '−', self._remove_dir, font_size=10,
                 fg=C['red'], bg=C['surface3']
                 ).pack(fill='x', pady=1, ipady=4, padx=2)

        self._refresh_dirs()

        make_btn(self, '↻ Rescan Library', self._rescan, font_size=9,
                 fg=C['accent'], bg=C['surface2']
                 ).pack(fill='x', padx=6, pady=4, ipady=6)

        tk.Frame(self, bg=C['border'], height=1).pack(fill='x', padx=6)

        # Brightness (via sysfs)
        tk.Label(self, text='SCREEN BRIGHTNESS', font=('DejaVu Sans Mono', 7),
                 fg=C['mute'], bg=C['bg'], anchor='w'
                 ).pack(fill='x', padx=6, pady=(6, 0))

        bright_f = tk.Frame(self, bg=C['bg'])
        bright_f.pack(fill='x', padx=6)

        self.bright_cv = tk.Canvas(bright_f, height=20, bg=C['bg'],
                                    highlightthickness=0, cursor='hand2')
        self.bright_cv.pack(fill='x', expand=True)
        self.bright_cv.bind('<ButtonPress-1>',   self._bright_set)
        self.bright_cv.bind('<B1-Motion>',       self._bright_set)
        self._bright_pct = self._get_brightness()
        self._draw_bright()

        tk.Frame(self, bg=C['border'], height=1).pack(fill='x', padx=6, pady=4)

        # System buttons
        sys_f = tk.Frame(self, bg=C['bg'])
        sys_f.pack(fill='x', padx=6, pady=4)

        make_btn(sys_f, '⏻ Shutdown', self._shutdown, font_size=9,
                 fg=C['red'], bg=C['surface2']
                 ).pack(side='left', fill='x', expand=True, padx=(0, 2), ipady=6)

        make_btn(sys_f, '↺ Restart', self._restart, font_size=9,
                 fg=C['accent'], bg=C['surface2']
                 ).pack(side='left', fill='x', expand=True, padx=(2, 0), ipady=6)

        self.status_lbl = tk.Label(self, text='', font=('DejaVu Sans', 7),
                                    fg=C['accent'], bg=C['bg'])
        self.status_lbl.pack()

    def _refresh_dirs(self):
        self.dir_lb.delete(0, 'end')
        for d in self.app.config.get('music_dirs', []):
            self.dir_lb.insert('end', f' {d}')

    def _add_dir(self):
        # On Pi without file dialog, type a path
        win = tk.Toplevel(self.app.root)
        win.title('Add Folder')
        win.geometry('280x100')
        win.configure(bg=C['bg'])
        win.grab_set()

        tk.Label(win, text='Enter folder path:', font=('DejaVu Sans', 9),
                 fg=C['text'], bg=C['bg']).pack(pady=6)

        var = tk.StringVar(value=str(Path.home() / 'Music'))
        e = tk.Entry(win, textvariable=var, font=('DejaVu Sans', 9),
                     fg=C['text'], bg=C['surface3'],
                     insertbackground=C['accent'], relief='flat')
        e.pack(fill='x', padx=10)

        def ok():
            path = var.get().strip()
            if path and os.path.isdir(path):
                dirs = self.app.config.setdefault('music_dirs', [])
                if path not in dirs:
                    dirs.append(path)
                    save_config(self.app.config)
                    self._refresh_dirs()
            win.destroy()

        make_btn(win, 'Add', ok, font_size=9, fg=C['green'],
                 bg=C['surface2']).pack(pady=6, ipadx=20)

    def _remove_dir(self):
        sel = self.dir_lb.curselection()
        if sel:
            dirs = self.app.config.get('music_dirs', [])
            if sel[0] < len(dirs):
                dirs.pop(sel[0])
                save_config(self.app.config)
                self._refresh_dirs()

    def _rescan(self):
        self.status_lbl.config(text='Scanning…')
        self.app.root.update()
        self.app.reload_tracks()
        self.status_lbl.config(text=f'{len(self.app.tracks)} tracks found')
        self.after(2000, lambda: self.status_lbl.config(text=''))

    def _bright_set(self, e):
        w = self.bright_cv.winfo_width() or 200
        pct = max(0.1, min(1.0, e.x / w))
        self._bright_pct = pct
        self._draw_bright()
        self._set_brightness(pct)

    def _draw_bright(self):
        self.bright_cv.delete('all')
        w = self.bright_cv.winfo_width() or 200
        self.bright_cv.create_rectangle(0, 7, w, 13, fill=C['surface3'], outline='')
        fw = int(w * self._bright_pct)
        if fw > 0:
            self.bright_cv.create_rectangle(0, 7, fw, 13, fill=C['accent2'], outline='')
        tx = max(8, min(w-8, fw))
        self.bright_cv.create_oval(tx-6, 4, tx+6, 16, fill=C['accent2'], outline='')
        pct_txt = f'{int(self._bright_pct * 100)}%'
        self.bright_cv.create_text(w//2, 10, text=pct_txt,
                                    font=('DejaVu Sans Mono', 7), fill=C['text'])

    def _get_brightness(self):
        try:
            paths = [
                '/sys/class/backlight/rpi_backlight/brightness',
                '/sys/class/backlight/10-0045/brightness',
            ]
            max_paths = [p.replace('brightness', 'max_brightness') for p in paths]
            for bp, mp in zip(paths, max_paths):
                if os.path.exists(bp) and os.path.exists(mp):
                    b = int(open(bp).read())
                    m = int(open(mp).read())
                    return b / m
        except:
            pass
        return 0.8

    def _set_brightness(self, pct):
        try:
            paths = [
                '/sys/class/backlight/rpi_backlight/brightness',
                '/sys/class/backlight/10-0045/brightness',
            ]
            max_paths = [p.replace('brightness', 'max_brightness') for p in paths]
            for bp, mp in zip(paths, max_paths):
                if os.path.exists(bp) and os.path.exists(mp):
                    m = int(open(mp).read())
                    val = max(10, int(pct * m))
                    with open(bp, 'w') as f:
                        f.write(str(val))
                    return
        except:
            pass

    def _shutdown(self):
        self.app.player.stop()
        save_config(self.app.config)
        subprocess.run(['sudo', 'shutdown', '-h', 'now'])

    def _restart(self):
        self.app.player.stop()
        save_config(self.app.config)
        subprocess.run(['sudo', 'reboot'])


# ─── Visualizer ───────────────────────────────────────────────────────────────

class VisualizerBar(tk.Canvas):
    def __init__(self, parent, height=30, **kw):
        super().__init__(parent, height=height, bg=C['bg'],
                         highlightthickness=0, **kw)
        self.bars    = 20
        self.heights = [0.0] * self.bars
        self.targets = [0.0] * self.bars
        self.playing = False
        self._anim()

    def set_playing(self, on):
        self.playing = on
        if on:
            self._randomize()

    def _randomize(self):
        if self.playing:
            for i in range(self.bars):
                self.targets[i] = (random.uniform(0.1, 0.95)
                                   if random.random() > 0.15
                                   else random.uniform(0.02, 0.15))
            self.after(random.randint(80, 220), self._randomize)

    def _anim(self):
        for i in range(self.bars):
            diff = self.targets[i] - self.heights[i]
            self.heights[i] += diff * 0.2
            if not self.playing:
                self.targets[i] *= 0.9
                self.heights[i] *= 0.85
        self._draw()
        self.after(40, self._anim)

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        bw = w / self.bars
        gap = max(1, bw * 0.3)
        for i, ht in enumerate(self.heights):
            x1 = i * bw + gap / 2
            x2 = x1 + bw - gap
            bh = max(1, ht * h)
            col = C['accent2'] if ht > 0.65 else (C['accent'] if ht > 0.35 else C['adim'])
            self.create_rectangle(x1, h - bh, x2, h, fill=col, outline='')


# ─── GPIO Button Handler ──────────────────────────────────────────────────────

class GPIOHandler:
    """Maps the 4 PiTFT side buttons to player actions."""

    def __init__(self, app):
        self.app = app
        self._available = False
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in GPIO_BTNS:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # Button assignments:
            # GPIO17 (top)    → Play/Pause
            # GPIO22          → Previous track
            # GPIO23          → Next track
            # GPIO27 (bottom) → Volume toggle (mute/unmute)
            GPIO.add_event_detect(GPIO_BTNS[0], GPIO.FALLING,
                callback=lambda _: app.root.after(0, app.toggle_play), bouncetime=300)
            GPIO.add_event_detect(GPIO_BTNS[1], GPIO.FALLING,
                callback=lambda _: app.root.after(0, app.prev_track), bouncetime=300)
            GPIO.add_event_detect(GPIO_BTNS[2], GPIO.FALLING,
                callback=lambda _: app.root.after(0, app.next_track), bouncetime=300)
            GPIO.add_event_detect(GPIO_BTNS[3], GPIO.FALLING,
                callback=lambda _: app.root.after(0, app.toggle_mute), bouncetime=300)
            self._available = True
        except (ImportError, RuntimeError):
            pass  # Not on Pi or GPIO not available — that's fine

    def cleanup(self):
        if self._available:
            try:
                self.GPIO.cleanup()
            except:
                pass


# ─── Main App ─────────────────────────────────────────────────────────────────

class WalkmanApp:
    def __init__(self, root):
        self.root   = root
        self.config = load_config()
        self.player = Player()
        self.player.on_end  = self._on_track_end
        self.player.on_tick = self._on_tick

        self.tracks        = []
        self.current_index = -1
        self.shuffle       = self.config.get('shuffle', False)
        self.repeat        = self.config.get('repeat', 'none')
        self._muted        = False
        self._premute_vol  = self.config.get('volume', 85)

        self.player.set_volume(self.config.get('volume', 85))

        # Root window setup — fixed 320×240
        root.title('Walkman')
        root.geometry(f'{SCREEN_W}x{SCREEN_H}')
        root.resizable(False, False)
        root.configure(bg=C['bg'])
        root.attributes('-fullscreen', True)  # Fullscreen on PiTFT

        self._build_views()
        self.gpio = GPIOHandler(self)

        self.reload_tracks()
        self.show_view('player')

        root.protocol('WM_DELETE_WINDOW', self._quit)
        root.bind('<Escape>', lambda e: self._quit())
        # Keyboard shortcuts for dev/testing
        root.bind('<space>',      lambda e: self.toggle_play())
        root.bind('<Left>',       lambda e: self.prev_track())
        root.bind('<Right>',      lambda e: self.next_track())
        root.bind('<Up>',         lambda e: self._vol_step(5))
        root.bind('<Down>',       lambda e: self._vol_step(-5))

    def _build_views(self):
        self.container = tk.Frame(self.root, bg=C['bg'])
        self.container.pack(fill='both', expand=True)

        self.player_view    = PlayerView(self.container, self)
        self.library_view   = LibraryView(self.container, self)
        self.bluetooth_view = BluetoothView(self.container, self)
        self.settings_view  = SettingsView(self.container, self)

        self._views = {
            'player':    self.player_view,
            'library':   self.library_view,
            'bluetooth': self.bluetooth_view,
            'settings':  self.settings_view,
        }
        self._current_view = None

    def show_view(self, name):
        if self._current_view:
            self._current_view.pack_forget()
        view = self._views[name]
        view.pack(fill='both', expand=True)
        self._current_view = view
        if name == 'bluetooth':
            self.bluetooth_view.on_show()

    # ── Track Management ─────────────────────────────────────────────────────

    def reload_tracks(self):
        self.tracks = scan_dirs(self.config.get('music_dirs', []))
        self.library_view.set_tracks(self.tracks)

    def play_index(self, index):
        if not self.tracks or not (0 <= index < len(self.tracks)):
            return
        self.current_index = index
        track = self.tracks[index]
        ok = self.player.play(track['path'], video=(track['type'] == 'video'))
        if not ok:
            return
        self.player_view.update_track(track)
        self.player_view.update_play_state(True, False)
        self.library_view.highlight(index)

    def toggle_play(self):
        if not self.player.playing:
            if self.tracks:
                idx = self.current_index if self.current_index >= 0 else 0
                self.play_index(idx)
            return
        self.player.pause()
        self.player_view.update_play_state(True, self.player.paused)

    def prev_track(self):
        if not self.tracks: return
        idx = (self.current_index - 1) % len(self.tracks)
        self.play_index(idx)

    def next_track(self):
        if not self.tracks: return
        if self.shuffle:
            idx = random.randint(0, len(self.tracks) - 1)
        else:
            idx = (self.current_index + 1) % len(self.tracks)
        self.play_index(idx)

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.config['shuffle'] = self.shuffle
        self.player_view.update_shuffle(self.shuffle)
        self.player_view.update_mode(self.shuffle, self.repeat)

    def cycle_repeat(self):
        modes = ['none', 'all', 'one']
        self.repeat = modes[(modes.index(self.repeat) + 1) % 3]
        self.config['repeat'] = self.repeat
        self.player_view.update_repeat(self.repeat)
        self.player_view.update_mode(self.shuffle, self.repeat)

    def seek_to(self, pct):
        if self.player.dur > 0:
            self.player.seek(pct * self.player.dur)

    def set_volume(self, v):
        self.player.set_volume(v)
        self.config['volume'] = v
        self.player_view.update_volume(v)
        self._premute_vol = v

    def toggle_mute(self):
        if self._muted:
            self._muted = False
            self.set_volume(self._premute_vol)
        else:
            self._premute_vol = self.player.volume
            self._muted = True
            self.player.set_volume(0)
            self.player_view.update_volume(0)

    def _vol_step(self, delta):
        v = max(0, min(100, self.player.volume + delta))
        self.set_volume(v)

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _on_track_end(self):
        self.root.after(100, self._handle_end)

    def _handle_end(self):
        self.player_view.update_play_state(False, False)
        if self.repeat == 'one':
            self.play_index(self.current_index)
        elif self.repeat == 'all' or self.current_index < len(self.tracks) - 1:
            self.next_track()

    def _on_tick(self, pos, dur):
        self.root.after(0, self.player_view.update_position, pos, dur)

    # ── Quit ─────────────────────────────────────────────────────────────────

    def _quit(self):
        self.player.stop()
        self.gpio.cleanup()
        save_config(self.config)
        self.root.destroy()


# ─── Entry ────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    # Hide cursor on touchscreen
    root.config(cursor='none')
    app = WalkmanApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
