#!/usr/bin/env python3
"""
Sony Walkman Player for Raspberry Pi
A retro-modern music & music video player with a clean, beautiful UI.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import json
import time
import math
import random
from pathlib import Path
import sys

# ─── Constants ────────────────────────────────────────────────────────────────

MUSIC_EXTENSIONS = {'.mp3', '.flac', '.wav', '.ogg', '.aac', '.m4a', '.opus', '.wma'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.flv', '.mpg', '.mpeg'}

CONFIG_FILE = Path.home() / '.walkman_config.json'

# ─── Color Palette ────────────────────────────────────────────────────────────

COLORS = {
    'bg':           '#0A0A0F',
    'surface':      '#12121A',
    'surface2':     '#1A1A26',
    'surface3':     '#22222F',
    'border':       '#2A2A3A',
    'accent':       '#FF6B35',
    'accent2':      '#FF9500',
    'accent_dim':   '#7A3218',
    'text':         '#E8E8F0',
    'text_dim':     '#8888A0',
    'text_mute':    '#44445A',
    'green':        '#4ADE80',
    'red':          '#FF4444',
    'blue':         '#60A5FA',
    'vis1':         '#FF6B35',
    'vis2':         '#FF9500',
    'vis3':         '#FFD700',
}

# ─── Config ───────────────────────────────────────────────────────────────────

def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except:
        pass
    return {'music_dirs': [], 'volume': 80, 'last_track': None, 'shuffle': False, 'repeat': 'none'}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except:
        pass

# ─── Track Scanner ────────────────────────────────────────────────────────────

def scan_directory(path):
    tracks = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for f in sorted(files):
            ext = Path(f).suffix.lower()
            if ext in MUSIC_EXTENSIONS | VIDEO_EXTENSIONS:
                full = os.path.join(root, f)
                tracks.append({
                    'path': full,
                    'name': Path(f).stem,
                    'ext': ext,
                    'type': 'video' if ext in VIDEO_EXTENSIONS else 'music',
                    'size': os.path.getsize(full),
                })
    return tracks

# ─── MPV Player Wrapper ───────────────────────────────────────────────────────

class MPVPlayer:
    def __init__(self):
        self.process = None
        self.ipc_socket = '/tmp/walkman_mpv_ipc'
        self.volume = 80
        self.playing = False
        self.paused = False
        self._duration = 0
        self._position = 0
        self._lock = threading.Lock()
        self._pos_thread = None
        self._running = False
        self.on_end = None
        self.on_position = None

    def _send_ipc(self, cmd):
        try:
            import socket, json
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.ipc_socket)
            s.send((json.dumps(cmd) + '\n').encode())
            time.sleep(0.05)
            try:
                s.settimeout(0.3)
                data = s.recv(4096).decode()
                s.close()
                return data
            except:
                s.close()
        except:
            pass
        return None

    def play(self, path, video=False):
        self.stop()
        self.playing = True
        self.paused = False
        cmd = [
            'mpv',
            '--input-ipc-server=' + self.ipc_socket,
            f'--volume={self.volume}',
            '--no-terminal',
        ]
        if not video:
            cmd += ['--no-video', '--audio-display=no']
        else:
            cmd += ['--fs']
        cmd.append(path)

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            messagebox.showerror("MPV Not Found",
                "Please install mpv:\n  sudo apt install mpv")
            self.playing = False
            return

        self._running = True
        self._pos_thread = threading.Thread(target=self._monitor, daemon=True)
        self._pos_thread.start()

    def _monitor(self):
        time.sleep(0.5)
        while self._running and self.process and self.process.poll() is None:
            # Query position
            r = self._send_ipc({"command": ["get_property", "time-pos"]})
            if r:
                try:
                    import json as j
                    for line in r.strip().split('\n'):
                        obj = j.loads(line)
                        if obj.get('error') == 'success':
                            self._position = float(obj.get('data', 0) or 0)
                except:
                    pass
            # Query duration
            r2 = self._send_ipc({"command": ["get_property", "duration"]})
            if r2:
                try:
                    import json as j
                    for line in r2.strip().split('\n'):
                        obj = j.loads(line)
                        if obj.get('error') == 'success':
                            self._duration = float(obj.get('data', 0) or 0)
                except:
                    pass
            if self.on_position:
                self.on_position(self._position, self._duration)
            time.sleep(0.5)

        if self._running:
            self.playing = False
            self.paused = False
            if self.on_end:
                self.on_end()
        self._running = False

    def pause(self):
        self._send_ipc({"command": ["cycle", "pause"]})
        self.paused = not self.paused

    def stop(self):
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try: self.process.kill()
                except: pass
        self.process = None
        self.playing = False
        self.paused = False
        self._position = 0
        self._duration = 0

    def seek(self, seconds):
        self._send_ipc({"command": ["seek", seconds, "absolute"]})

    def set_volume(self, vol):
        self.volume = max(0, min(100, int(vol)))
        self._send_ipc({"command": ["set_property", "volume", self.volume]})

    def get_position(self):
        return self._position, self._duration


# ─── Animated Visualizer Canvas ───────────────────────────────────────────────

class VisualizerCanvas(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.bars = 32
        self.heights = [0.0] * self.bars
        self.targets = [0.0] * self.bars
        self.playing = False
        self.configure(bg=COLORS['bg'], highlightthickness=0)
        self._animate()

    def set_playing(self, playing):
        self.playing = playing
        if playing:
            self._randomize()

    def _randomize(self):
        if self.playing:
            for i in range(self.bars):
                self.targets[i] = random.uniform(0.05, 0.95) if random.random() > 0.2 else random.uniform(0.02, 0.2)
            self.after(random.randint(80, 200), self._randomize)

    def _animate(self):
        for i in range(self.bars):
            diff = self.targets[i] - self.heights[i]
            self.heights[i] += diff * 0.18
            if not self.playing:
                self.targets[i] *= 0.92
                self.heights[i] *= 0.88

        self._draw()
        self.after(33, self._animate)

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        bar_w = w / self.bars
        gap = max(1, bar_w * 0.25)
        bw = bar_w - gap

        for i, ht in enumerate(self.heights):
            x1 = i * bar_w + gap / 2
            x2 = x1 + bw
            bar_h = max(2, ht * h)
            y1 = h - bar_h
            y2 = h

            # Gradient color based on height
            if ht > 0.7:
                color = COLORS['accent2']
            elif ht > 0.4:
                color = COLORS['accent']
            else:
                color = COLORS['accent_dim']

            self.create_rectangle(x1, y1, x2, y2, fill=color, outline='', tags='bar')

            # Top glow dot
            if ht > 0.1:
                self.create_rectangle(x1, y1, x2, y1 + 2, fill=COLORS['accent2'], outline='')


# ─── Track List Widget ────────────────────────────────────────────────────────

class TrackList(tk.Frame):
    def __init__(self, parent, on_select, **kwargs):
        super().__init__(parent, bg=COLORS['surface'], **kwargs)
        self.on_select = on_select
        self.tracks = []
        self.current_index = -1
        self._build()

    def _build(self):
        # Search bar
        search_frame = tk.Frame(self, bg=COLORS['surface2'], pady=8, padx=8)
        search_frame.pack(fill='x')

        tk.Label(search_frame, text='⌕', font=('DejaVu Sans', 14),
                 fg=COLORS['text_dim'], bg=COLORS['surface2']).pack(side='left', padx=(4, 6))

        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._on_search)
        entry = tk.Entry(search_frame, textvariable=self.search_var,
                         bg=COLORS['surface3'], fg=COLORS['text'],
                         insertbackground=COLORS['accent'],
                         relief='flat', font=('DejaVu Sans', 11),
                         bd=0)
        entry.pack(fill='x', expand=True, ipady=4)

        # Track count label
        self.count_label = tk.Label(self, text='No tracks loaded',
                                    font=('DejaVu Sans', 9),
                                    fg=COLORS['text_mute'], bg=COLORS['surface'],
                                    pady=4)
        self.count_label.pack(fill='x', padx=8)

        # Listbox with scrollbar
        list_frame = tk.Frame(self, bg=COLORS['surface'])
        list_frame.pack(fill='both', expand=True)

        self.scrollbar = tk.Scrollbar(list_frame, orient='vertical',
                                      bg=COLORS['surface3'], troughcolor=COLORS['surface'],
                                      relief='flat', bd=0, width=8)
        self.scrollbar.pack(side='right', fill='y')

        self.listbox = tk.Listbox(
            list_frame,
            bg=COLORS['surface'],
            fg=COLORS['text_dim'],
            selectbackground=COLORS['accent_dim'],
            selectforeground=COLORS['accent2'],
            activestyle='none',
            font=('DejaVu Sans', 10),
            relief='flat',
            bd=0,
            highlightthickness=0,
            yscrollcommand=self.scrollbar.set,
            cursor='hand2',
        )
        self.listbox.pack(side='left', fill='both', expand=True)
        self.scrollbar.config(command=self.listbox.yview)
        self.listbox.bind('<Double-Button-1>', self._on_double_click)
        self.listbox.bind('<Return>', self._on_double_click)

        self._filtered = []

    def set_tracks(self, tracks):
        self.tracks = tracks
        self._filter('')
        self.count_label.config(text=f'{len(tracks)} tracks')

    def _on_search(self, *_):
        self._filter(self.search_var.get())

    def _filter(self, query):
        q = query.lower()
        self._filtered = [t for t in self.tracks if q in t['name'].lower()] if q else self.tracks[:]
        self.listbox.delete(0, 'end')
        for t in self._filtered:
            icon = '▶' if t['type'] == 'video' else '♪'
            self.listbox.insert('end', f'  {icon}  {t["name"]}')

    def _on_double_click(self, event=None):
        sel = self.listbox.curselection()
        if sel and self._filtered:
            idx = sel[0]
            track = self._filtered[idx]
            real_idx = self.tracks.index(track)
            self.on_select(real_idx)

    def highlight(self, index):
        self.current_index = index
        self.listbox.selection_clear(0, 'end')
        # Find position in filtered list
        if 0 <= index < len(self.tracks):
            track = self.tracks[index]
            if track in self._filtered:
                pos = self._filtered.index(track)
                self.listbox.selection_set(pos)
                self.listbox.see(pos)


# ─── Main Application ─────────────────────────────────────────────────────────

class WalkmanApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Walkman')
        self.root.configure(bg=COLORS['bg'])
        self.root.geometry('900x600')
        self.root.minsize(700, 480)

        self.config = load_config()
        self.player = MPVPlayer()
        self.player.on_end = self._on_track_end
        self.player.on_position = self._on_position_update
        self.player.set_volume(self.config.get('volume', 80))

        self.tracks = []
        self.current_index = -1
        self.shuffle = self.config.get('shuffle', False)
        self.repeat = self.config.get('repeat', 'none')  # none / one / all
        self._seek_dragging = False

        self._build_ui()
        self._load_saved_dirs()

        self.root.protocol('WM_DELETE_WINDOW', self._on_quit)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        topbar = tk.Frame(self.root, bg=COLORS['surface'], height=50)
        topbar.pack(fill='x')
        topbar.pack_propagate(False)

        logo = tk.Label(topbar, text='WALKMAN', font=('DejaVu Sans Mono', 16, 'bold'),
                        fg=COLORS['accent'], bg=COLORS['surface'], padx=20)
        logo.pack(side='left', pady=8)

        sub = tk.Label(topbar, text='DIGITAL MEDIA PLAYER',
                       font=('DejaVu Sans', 7, 'bold'), fg=COLORS['text_mute'],
                       bg=COLORS['surface'])
        sub.place(in_=logo, relx=0.0, rely=1.0, anchor='nw', x=20, y=-14)

        # Add folder button
        add_btn = tk.Button(topbar, text='＋ Add Folder',
                            font=('DejaVu Sans', 10),
                            fg=COLORS['text'], bg=COLORS['surface3'],
                            activeforeground=COLORS['accent2'],
                            activebackground=COLORS['surface3'],
                            relief='flat', bd=0, padx=14, pady=6,
                            cursor='hand2',
                            command=self._add_folder)
        add_btn.pack(side='right', padx=10, pady=8)

        # Filter buttons
        self.filter_var = tk.StringVar(value='all')
        for label, val in [('All', 'all'), ('Music', 'music'), ('Video', 'video')]:
            rb = tk.Radiobutton(topbar, text=label, variable=self.filter_var,
                                value=val,
                                font=('DejaVu Sans', 9),
                                fg=COLORS['text_dim'], bg=COLORS['surface'],
                                selectcolor=COLORS['surface'],
                                activebackground=COLORS['surface'],
                                activeforeground=COLORS['accent'],
                                indicatoron=False,
                                relief='flat', bd=0,
                                padx=10, pady=5,
                                cursor='hand2',
                                command=self._apply_filter)
            rb.pack(side='right', padx=2)

        # Main content area
        main = tk.PanedWindow(self.root, orient='horizontal',
                              bg=COLORS['border'], sashwidth=3,
                              sashrelief='flat')
        main.pack(fill='both', expand=True)

        # Left: track list
        self.tracklist = TrackList(main, on_select=self._play_index)
        main.add(self.tracklist, minsize=220, width=300)

        # Right: player panel
        right = tk.Frame(main, bg=COLORS['bg'])
        main.add(right, minsize=380)

        self._build_player_panel(right)

    def _build_player_panel(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=0)
        parent.grid_columnconfigure(0, weight=1)

        # Top section (album art + visualizer + info)
        top = tk.Frame(parent, bg=COLORS['bg'])
        top.grid(row=0, column=0, sticky='nsew', padx=24, pady=(20, 0))
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(2, weight=1)

        # Album art placeholder
        art_frame = tk.Frame(top, bg=COLORS['surface2'], width=180, height=180)
        art_frame.grid(row=0, column=0, pady=(0, 0))
        art_frame.grid_propagate(False)

        self.art_canvas = tk.Canvas(art_frame, bg=COLORS['surface2'],
                                    highlightthickness=0, width=180, height=180)
        self.art_canvas.place(relx=0.5, rely=0.5, anchor='center')
        self._draw_art_placeholder()

        # Track info
        info_frame = tk.Frame(top, bg=COLORS['bg'])
        info_frame.grid(row=1, column=0, sticky='ew', pady=(16, 8))
        info_frame.grid_columnconfigure(0, weight=1)

        self.title_label = tk.Label(info_frame, text='No track selected',
                                     font=('DejaVu Serif', 14, 'bold'),
                                     fg=COLORS['text'], bg=COLORS['bg'],
                                     wraplength=300, justify='center')
        self.title_label.grid(row=0, column=0)

        self.type_label = tk.Label(info_frame, text='—',
                                    font=('DejaVu Sans Mono', 9),
                                    fg=COLORS['accent'], bg=COLORS['bg'], pady=2)
        self.type_label.grid(row=1, column=0)

        # Visualizer
        self.visualizer = VisualizerCanvas(top, height=60)
        self.visualizer.grid(row=2, column=0, sticky='ew', pady=(4, 0))

        # Bottom controls section
        controls = tk.Frame(parent, bg=COLORS['surface'], pady=0)
        controls.grid(row=1, column=0, sticky='ew')
        controls.grid_columnconfigure(0, weight=1)

        # Progress / seek bar
        seek_frame = tk.Frame(controls, bg=COLORS['surface'])
        seek_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=(14, 0))
        seek_frame.grid_columnconfigure(1, weight=1)

        self.time_label = tk.Label(seek_frame, text='0:00',
                                    font=('DejaVu Sans Mono', 9),
                                    fg=COLORS['text_dim'], bg=COLORS['surface'], width=5)
        self.time_label.grid(row=0, column=0)

        self.seek_var = tk.DoubleVar(value=0)
        self.seek_bar = ttk.Scale(seek_frame, variable=self.seek_var,
                                   from_=0, to=100, orient='horizontal',
                                   command=self._on_seek_drag)
        self._style_seek()
        self.seek_bar.grid(row=0, column=1, sticky='ew', padx=8)
        self.seek_bar.bind('<ButtonPress-1>', lambda e: setattr(self, '_seek_dragging', True))
        self.seek_bar.bind('<ButtonRelease-1>', self._on_seek_release)

        self.dur_label = tk.Label(seek_frame, text='0:00',
                                   font=('DejaVu Sans Mono', 9),
                                   fg=COLORS['text_dim'], bg=COLORS['surface'], width=5)
        self.dur_label.grid(row=0, column=2)

        # Main transport controls
        transport = tk.Frame(controls, bg=COLORS['surface'])
        transport.grid(row=1, column=0, pady=10)

        btn_cfg = dict(font=('DejaVu Sans', 16), bg=COLORS['surface'],
                       activebackground=COLORS['surface'], relief='flat', bd=0,
                       cursor='hand2', padx=6, pady=4)

        self.shuffle_btn = tk.Button(transport, text='⇀',
                                      fg=COLORS['accent'] if self.shuffle else COLORS['text_mute'],
                                      command=self._toggle_shuffle, **btn_cfg)
        self.shuffle_btn.grid(row=0, column=0, padx=4)

        tk.Button(transport, text='⏮', fg=COLORS['text_dim'],
                  command=self._prev, activeforeground=COLORS['accent'],
                  **btn_cfg).grid(row=0, column=1, padx=4)

        self.play_btn = tk.Button(transport, text='▶',
                                   font=('DejaVu Sans', 22),
                                   fg=COLORS['accent'], bg=COLORS['accent_dim'],
                                   activebackground=COLORS['accent_dim'],
                                   activeforeground=COLORS['accent2'],
                                   relief='flat', bd=0, padx=12, pady=6,
                                   cursor='hand2',
                                   command=self._toggle_play)
        self.play_btn.grid(row=0, column=2, padx=8)

        tk.Button(transport, text='⏭', fg=COLORS['text_dim'],
                  command=self._next, activeforeground=COLORS['accent'],
                  **btn_cfg).grid(row=0, column=3, padx=4)

        repeat_symbols = {'none': '↺', 'all': '↺', 'one': '↻'}
        self.repeat_btn = tk.Button(transport, text=repeat_symbols[self.repeat],
                                     fg=COLORS['accent'] if self.repeat != 'none' else COLORS['text_mute'],
                                     command=self._cycle_repeat, **btn_cfg)
        self.repeat_btn.grid(row=0, column=4, padx=4)

        # Volume
        vol_frame = tk.Frame(controls, bg=COLORS['surface'])
        vol_frame.grid(row=2, column=0, pady=(0, 12))

        tk.Label(vol_frame, text='🔈', font=('DejaVu Sans', 11),
                 fg=COLORS['text_mute'], bg=COLORS['surface']).pack(side='left', padx=4)

        self.vol_var = tk.IntVar(value=self.config.get('volume', 80))
        vol_slider = ttk.Scale(vol_frame, variable=self.vol_var,
                               from_=0, to=100, orient='horizontal',
                               length=140, command=self._on_volume)
        vol_slider.pack(side='left')

        tk.Label(vol_frame, text='🔊', font=('DejaVu Sans', 11),
                 fg=COLORS['text_dim'], bg=COLORS['surface']).pack(side='left', padx=4)

        self.vol_label = tk.Label(vol_frame, text=f'{self.vol_var.get()}%',
                                   font=('DejaVu Sans Mono', 9),
                                   fg=COLORS['text_dim'], bg=COLORS['surface'], width=4)
        self.vol_label.pack(side='left')

    def _style_seek(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Horizontal.TScale',
                         troughcolor=COLORS['surface3'],
                         background=COLORS['accent'],
                         sliderlength=14,
                         sliderrelief='flat')

    def _draw_art_placeholder(self):
        c = self.art_canvas
        c.delete('all')
        c.create_rectangle(0, 0, 180, 180, fill=COLORS['surface2'], outline='')
        # Decorative circles
        c.create_oval(50, 50, 130, 130, outline=COLORS['border'], width=2)
        c.create_oval(70, 70, 110, 110, fill=COLORS['surface3'], outline=COLORS['border'], width=2)
        c.create_oval(82, 82, 98, 98, fill=COLORS['accent_dim'], outline='')
        c.create_text(90, 145, text='No Track', font=('DejaVu Sans', 9),
                      fill=COLORS['text_mute'])

    def _draw_art_playing(self, track):
        c = self.art_canvas
        c.delete('all')
        c.create_rectangle(0, 0, 180, 180, fill=COLORS['surface2'], outline='')

        if track['type'] == 'video':
            # Film icon
            c.create_rectangle(30, 50, 150, 130, fill=COLORS['surface3'], outline=COLORS['border'], width=2)
            for x in [30, 50, 70, 90, 110, 130, 150]:
                c.create_rectangle(x-4, 45, x+4, 55, fill=COLORS['accent_dim'], outline='')
                c.create_rectangle(x-4, 125, x+4, 135, fill=COLORS['accent_dim'], outline='')
            # Play triangle
            c.create_polygon(75, 72, 75, 108, 115, 90, fill=COLORS['accent'], outline='')
        else:
            # Music note
            c.create_oval(40, 40, 140, 140, outline=COLORS['accent_dim'], width=1)
            c.create_oval(55, 55, 125, 125, outline=COLORS['accent_dim'], width=1)
            c.create_oval(70, 70, 110, 110, fill=COLORS['surface3'], outline=COLORS['accent'], width=2)
            c.create_oval(83, 83, 97, 97, fill=COLORS['accent'], outline='')

        # Track name (truncated)
        name = track['name'][:20] + '…' if len(track['name']) > 20 else track['name']
        c.create_text(90, 153, text=name, font=('DejaVu Sans', 8),
                      fill=COLORS['text_dim'], width=170)

    # ── Playback Logic ───────────────────────────────────────────────────────

    def _play_index(self, index):
        if not self.tracks or index < 0 or index >= len(self.tracks):
            return
        self.current_index = index
        track = self.tracks[index]

        self.player.play(track['path'], video=(track['type'] == 'video'))

        self.title_label.config(text=track['name'])
        self.type_label.config(text=('▶  VIDEO' if track['type'] == 'video' else '♪  AUDIO'))
        self.play_btn.config(text='⏸')
        self.visualizer.set_playing(True)
        self._draw_art_playing(track)
        self.tracklist.highlight(index)
        self.seek_var.set(0)
        self.time_label.config(text='0:00')
        self.dur_label.config(text='0:00')

    def _toggle_play(self):
        if not self.player.playing and self.current_index < 0:
            if self.tracks:
                self._play_index(0)
            return

        if self.player.playing:
            self.player.pause()
            if self.player.paused:
                self.play_btn.config(text='▶')
                self.visualizer.set_playing(False)
            else:
                self.play_btn.config(text='⏸')
                self.visualizer.set_playing(True)

    def _prev(self):
        if not self.tracks: return
        idx = (self.current_index - 1) % len(self.tracks)
        self._play_index(idx)

    def _next(self):
        if not self.tracks: return
        if self.shuffle:
            idx = random.randint(0, len(self.tracks) - 1)
        else:
            idx = (self.current_index + 1) % len(self.tracks)
        self._play_index(idx)

    def _on_track_end(self):
        self.root.after(100, self._handle_track_end)

    def _handle_track_end(self):
        self.visualizer.set_playing(False)
        self.play_btn.config(text='▶')
        if self.repeat == 'one':
            self._play_index(self.current_index)
        elif self.repeat == 'all' or (self.current_index < len(self.tracks) - 1):
            self._next()

    def _on_position_update(self, pos, dur):
        self.root.after(0, self._update_seek, pos, dur)

    def _update_seek(self, pos, dur):
        if not self._seek_dragging:
            if dur > 0:
                self.seek_var.set((pos / dur) * 100)
            self.time_label.config(text=self._fmt_time(pos))
            self.dur_label.config(text=self._fmt_time(dur))

    def _on_seek_drag(self, val):
        if self._seek_dragging:
            pass  # just update display

    def _on_seek_release(self, event):
        self._seek_dragging = False
        pos, dur = self.player.get_position()
        if dur > 0:
            target = (self.seek_var.get() / 100) * dur
            self.player.seek(target)

    def _on_volume(self, val):
        v = int(float(val))
        self.player.set_volume(v)
        self.vol_label.config(text=f'{v}%')
        self.config['volume'] = v

    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.shuffle_btn.config(fg=COLORS['accent'] if self.shuffle else COLORS['text_mute'])
        self.config['shuffle'] = self.shuffle

    def _cycle_repeat(self):
        modes = ['none', 'all', 'one']
        self.repeat = modes[(modes.index(self.repeat) + 1) % 3]
        colors = {'none': COLORS['text_mute'], 'all': COLORS['accent'], 'one': COLORS['accent2']}
        symbols = {'none': '↺', 'all': '↺', 'one': '↻'}
        self.repeat_btn.config(fg=colors[self.repeat], text=symbols[self.repeat])
        self.config['repeat'] = self.repeat

    # ── Folder Management ────────────────────────────────────────────────────

    def _add_folder(self):
        path = filedialog.askdirectory(title='Select Music/Video Folder')
        if path and path not in self.config['music_dirs']:
            self.config['music_dirs'].append(path)
            self._reload_tracks()
            save_config(self.config)

    def _load_saved_dirs(self):
        if self.config.get('music_dirs'):
            self._reload_tracks()

    def _reload_tracks(self):
        all_tracks = []
        for d in self.config.get('music_dirs', []):
            if os.path.isdir(d):
                all_tracks.extend(scan_directory(d))
        self.tracks = all_tracks
        self._apply_filter()

    def _apply_filter(self):
        flt = self.filter_var.get() if hasattr(self, 'filter_var') else 'all'
        if flt == 'all':
            shown = self.tracks
        else:
            shown = [t for t in self.tracks if t['type'] == flt]
        self.tracklist.set_tracks(shown)

    # ── Utilities ────────────────────────────────────────────────────────────

    def _fmt_time(self, seconds):
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h:
            return f'{h}:{m:02d}:{s:02d}'
        return f'{m}:{s:02d}'

    def _on_quit(self):
        self.player.stop()
        save_config(self.config)
        self.root.destroy()


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.title('Walkman')

    # Try to set icon
    try:
        root.iconbitmap('/usr/share/pixmaps/walkman.xbm')
    except:
        pass

    # Fullscreen toggle with F11
    def toggle_fullscreen(event=None):
        root.attributes('-fullscreen', not root.attributes('-fullscreen'))
    def escape_fullscreen(event=None):
        root.attributes('-fullscreen', False)

    root.bind('<F11>', toggle_fullscreen)
    root.bind('<Escape>', escape_fullscreen)

    app = WalkmanApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
