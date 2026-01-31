import tkinter as tk
from tkinter import filedialog, OptionMenu, StringVar, Button, Label, Entry, messagebox, ttk
import json
import os
import zipfile
import shutil
import tempfile
import threading
import time
import random
import platform
if platform.system() == 'Windows':
    import ctypes
from pynput import keyboard
from pynput.keyboard import Controller as KeyController
from itertools import groupby

class RhythmCheatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RT Beacon v1")
        self.root.geometry("600x600")  # Extra room for new shit 💀
        self.root.resizable(True, True)
        self.root.wm_attributes("-topmost", True)

        self.temp_dir = None
        self.meta = None
        self.diff_data = None
        self.notes = None
        self.trigger_key = "["
        self.tuning_key = None  # NEW: For time-tuning 😈

        self.listener = None
        self.running = False
        self.sim_thread = None
        self.currently_pressed = set()
        self.kb = None
        self.song_start_ms = 0
        self.offset_adjust = 0  # NEW: Track adjustments for GUI

        # Windows timer fix
        self.is_windows = platform.system() == 'Windows'
        if self.is_windows:
            self.winmm = ctypes.windll.winmm

        # ─── GUI ───────────────────────────────────────────────────────────────
        self.import_btn = Button(root, text="Import .rtm File", command=self.import_rtm)
        self.import_btn.pack(pady=10)

        self.song_label = Label(root, text="Song: N/A")
        self.song_label.pack()
        self.artist_label = Label(root, text="Artist: N/A")
        self.artist_label.pack()
        self.mapper_label = Label(root, text="Mapper: N/A")
        self.mapper_label.pack()
        self.bpm_label = Label(root, text="BPM: N/A")
        self.bpm_label.pack()
        self.offset_label = Label(root, text="Offset: N/A")
        self.offset_label.pack()

        self.diff_var = StringVar(root)
        self.diff_var.set("No difficulties loaded 💀")
        self.diff_menu = OptionMenu(root, self.diff_var, self.diff_var.get())
        self.diff_menu.pack(pady=5)
        self.diff_var.trace("w", self.load_diff)

        ttk.Separator(root, orient='horizontal').pack(fill='x', pady=10)
        Label(root, text="Mod:").pack()
        self.mod_var = StringVar(root)
        self.mod_var.set("NoMod")
        mod_menu = OptionMenu(root, self.mod_var, "NoMod", "Nightcore")
        mod_menu.pack(pady=5)

        # NEW: Preset selector for hit windows 😈
        ttk.Separator(root, orient='horizontal').pack(fill='x', pady=10)
        Label(root, text="Hit Window Preset:").pack()
        self.preset_var = StringVar(root)
        self.preset_var.set("Default")
        preset_menu = OptionMenu(root, self.preset_var, "Default", "Smaller", "Tiny", "Tiniest")
        preset_menu.pack(pady=5)
        self.preset_var.trace("w", self.update_preset_label)

        self.preset_label = Label(root, text="Tap offsets: -60 to +40ms (bias -20ms) | Hold start: -50 to +50ms (bias -10ms) | End: -40 to +60ms (bias +5ms)")
        self.preset_label.pack(pady=5)

        self.trigger_label = Label(root, text="Trigger Key (e.g., '['):")
        self.trigger_label.pack()
        self.trigger_entry = Entry(root)
        self.trigger_entry.insert(0, self.trigger_key)
        self.trigger_entry.pack(pady=5)

        # NEW: Tuning key entry 🔥
        self.tuning_label = Label(root, text="Tuning Key (optional, e.g., 'f'):")
        self.tuning_label.pack()
        self.tuning_entry = Entry(root)
        self.tuning_entry.pack(pady=5)

        self.start_btn = Button(root, text="Start Scanning", state="disabled", 
                               command=self.start_scanning, bg="red", fg="white", 
                               font=("Arial", 12, "bold"))
        self.start_btn.pack(pady=10)

        self.stop_btn = Button(root, text="FORCE STOP 🔥", command=self.force_stop,
                              bg="#8B0000", fg="white", font=("Arial", 12, "bold"),
                              state="disabled")
        self.stop_btn.pack(pady=5)
        self.stop_btn.pack_forget()

        # NEW: Live timing indicator 😤
        self.timing_label = Label(root, text="Current Reference: Song Start @ N/A ms | Offset Adj: 0 ms")
        self.timing_label.pack(pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.cleanup)

        # Preset configs 😤 (Tweaked for human-like: lower jump_prob for rarer outliers, higher mult for bigger jumps)
        # If you want avg ~30ms like human chart, set tap_bias=30 (but widen high if needed to avoid clipping)
        self.presets = {
            "Default": {
                "tap_low": -45, "tap_high": 30, "tap_bias": (-45 + 30) / 2,
                "hold_start_low": -35, "hold_start_high": 40, "hold_start_bias": (-35 + 40) / 2,
                "hold_end_low": -30, "hold_end_high": 50, "hold_end_bias": (-30 + 50) / 2,
                "jitter_low": -8, "jitter_high": 8,
                "group_threshold": 12,
                "jump_prob": 0.05, "jump_mult": 3.0  # Rarer but bigger jumps for human tails 💀
            },
            "Smaller": {
                "tap_low": -30, "tap_high": 20, "tap_bias": (-30 + 20) / 2,
                "hold_start_low": -25, "hold_start_high": 25, "hold_start_bias": (-25 + 25) / 2,
                "hold_end_low": -20, "hold_end_high": 35, "hold_end_bias": (-20 + 35) / 2,
                "jitter_low": -5, "jitter_high": 5,
                "group_threshold": 9,
                "jump_prob": 0.05, "jump_mult": 3.0
            },
            "Tiny": {
                "tap_low": -18, "tap_high": 16, "tap_bias": (-18 + 16) / 2,
                "hold_start_low": -15, "hold_start_high": 16, "hold_start_bias": (-15 + 16) / 2,
                "hold_end_low": -12, "hold_end_high": 18, "hold_end_bias": (-12 + 18) / 2,
                "jitter_low": -4, "jitter_high": 4,
                "group_threshold": 8,
                "jump_prob": 0.05, "jump_mult": 3.0
            },
            "Tiniest": {
                "tap_low": -6, "tap_high": 6, "tap_bias": (-6 + 6) / 2,
                "hold_start_low": -6, "hold_start_high": 12, "hold_start_bias": (-6 + 12) / 2,
                "hold_end_low": -6, "hold_end_high": 15, "hold_end_bias": (-6 + 15) / 2,
                "jitter_low": -2, "jitter_high": 2,
                "group_threshold": 5,
                "jump_prob": 0.05, "jump_mult": 3.0
            }
        }

    def update_preset_label(self, *args):
        preset = self.preset_var.get()
        config = self.presets.get(preset, self.presets["Default"])
        label_text = f"Tap: {config['tap_low']} to +{config['tap_high']}ms (bias {config['tap_bias']:.1f}ms) | Hold start: {config['hold_start_low']} to +{config['hold_start_high']}ms (bias {config['hold_start_bias']:.1f}ms) | End: {config['hold_end_low']} to +{config['hold_end_high']}ms (bias {config['hold_end_bias']:.1f}ms)"
        self.preset_label.config(text=label_text)

    def import_rtm(self):
        file = filedialog.askopenfilename(filetypes=[("RTM files", "*.rtm")])
        if not file: return

        print(f"Importing {file}... 🚀")
        zip_path = file + ".zip"
        shutil.copy(file, zip_path)
        self.temp_dir = tempfile.mkdtemp()

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            os.remove(zip_path)
        except Exception as e:
            messagebox.showerror("Error", f"Zip failed: {e} 💀")
            return

        meta_path = os.path.join(self.temp_dir, "meta.json")
        if not os.path.exists(meta_path):
            messagebox.showerror("Error", "No meta.json in zip 💀")
            return

        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        self.song_label.config(text=f"Song: {self.meta.get('songName', 'N/A')}")
        self.artist_label.config(text=f"Artist: {self.meta.get('artistName', 'N/A')}")
        self.mapper_label.config(text=f"Mapper: {self.meta.get('mapper', 'N/A')}")
        self.bpm_label.config(text=f"BPM: {self.meta.get('bpm', 'N/A')}")
        self.offset_label.config(text=f"Offset: {self.meta.get('offset', 'N/A')}ms")

        menu = self.diff_menu["menu"]
        menu.delete(0, "end")
        diffs = self.meta.get("difficulties", [])
        if not diffs:
            menu.add_command(label="No difficulties found 💀")
            self.diff_var.set("No difficulties found 💀")
            return

        for d in diffs:
            menu.add_command(label=d["name"], command=tk._setit(self.diff_var, d["name"]))
        self.diff_var.set(diffs[0]["name"])
        print(f"Dropdown populated with {len(diffs)} difficulties ✅")

    def load_diff(self, *args):
        name = self.diff_var.get()
        if not name or "No difficulties" in name or not self.meta:
            self.start_btn.config(state="disabled")
            return

        for d in self.meta["difficulties"]:
            if d["name"] == name:
                fn = d["filename"]
                diff_path = os.path.join(self.temp_dir, fn)
                if not os.path.exists(diff_path):
                    messagebox.showerror("Error", f"Missing {fn} 💀")
                    return

                with open(diff_path, "r", encoding="utf-8") as f:
                    self.diff_data = json.load(f)

                self.notes = sorted(self.diff_data["notes"], key=lambda n: n.get("time") or n.get("startTime") or 0)
                print(f"Total notes: {len(self.notes)}")
                self.start_btn.config(state="normal")
                break

    def start_scanning(self):
        self.trigger_key = self.trigger_entry.get().strip()
        self.tuning_key = self.tuning_entry.get().strip().lower()  # NEW: Get tuning key
        if not self.trigger_key:
            messagebox.showerror("Error", "Set a trigger key dumbass 💀")
            return

        print(f"Waiting for trigger '{self.trigger_key}'... 😈")
        if self.tuning_key:
            print(f"Tuning enabled on key '{self.tuning_key}' 🔥")
        self.start_btn.config(state="disabled", text="Scanning...")
        self.import_btn.config(state="disabled")

        def on_press(key):
            try:
                if hasattr(key, 'char') and key.char and key.char.lower() == self.trigger_key.lower():
                    print("TRIGGER HIT → GO TIME 🚀")
                    return False
            except: pass

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.start()

        def wait():
            self.listener.join()
            self.root.after(0, self.simulate_map)
        threading.Thread(target=wait, daemon=True).start()

    def simulate_map(self):
        if not self.notes:
            messagebox.showinfo("Bruh", "No notes 💀")
            self.reset_ui()
            return

        self.running = True
        self.kb = KeyController()
        self.currently_pressed.clear()

        if self.is_windows:
            self.winmm.timeBeginPeriod(1)
            print("Windows timer resolution cranked to 1ms 😤")

        mod = self.mod_var.get()
        speed_multiplier = 1.5 if mod == "Nightcore" else 1.0  # Renamed for clarity, >1 means faster
        print(f"MOD ACTIVE: {mod} → ×{speed_multiplier} speed 😤")

        # Grab preset config 😈
        preset = self.preset_var.get()
        config = self.presets.get(preset, self.presets["Default"])
        print(f"Using preset: {preset} 🔥")

        trigger_ms = time.perf_counter() * 1000
        first_time = min((n.get("time") or n.get("startTime") or float("inf")) for n in self.notes)
        self.song_start_ms = trigger_ms - (first_time / speed_multiplier)  # FIXED: Divide for faster speed
        self.offset_adjust = 0
        self.update_timing_label()
        print(f"Song start ms: {self.song_start_ms:.3f}")

        # Start periodic GUI update
        self.periodic_update()

        # ─── HUMANIZED EVENTS ────────────────────────────────────────────────
        events = []
        tuned = False if self.tuning_key else True  # Track if tuned yet
        for note in self.notes:
            ntype = note.get("type", "tap")
            key = note["key"].lower()

            # NEW: Check for tuning on first matching tap/hold start
            is_tuning_note = (not tuned and key == self.tuning_key and ntype in ["tap", "hold"])
            if is_tuning_note:
                tuned = True
                perfect_ms = (note.get("time") or note.get("startTime") or 0) / speed_multiplier  # FIXED: Divide
                user_press_ms = self.wait_for_user_press(key)  # NEW: Wait for user
                if user_press_ms is None:
                    print("Tuning timed out, continuing without 💀")
                    continue
                delta = user_press_ms - (self.song_start_ms + perfect_ms)
                self.song_start_ms += delta
                self.offset_adjust += delta
                self.update_timing_label()
                print(f"TUNED! New song_start_ms: {self.song_start_ms:.3f} | Adj: {delta:.3f}ms 😈")
                # Still add the press if hold, but for tap, simulate release (assume user pressed down)
                if ntype == "tap":
                    hold_dur = random.uniform(35, 80)
                    events.append((perfect_ms, 'down', key))  # But skip if user did it? For sim, add anyway
                    events.append((perfect_ms + hold_dur / speed_multiplier, 'up', key))  # Adjust hold for speed?
                else:  # Hold, user pressed down, bot handles release
                    et = (note.get("endTime") or 0) / speed_multiplier  # FIXED
                    end_off = self.get_offset(config["hold_end_low"], config["hold_end_high"], config["hold_end_bias"], config)
                    events.append((et + end_off, 'up', key))
                continue

            if ntype == "tap":
                perfect_ms = (note.get("time") or 0) / speed_multiplier  # FIXED: Divide for faster
                offset = self.get_offset(config["tap_low"], config["tap_high"], config["tap_bias"], config)
                press_time = perfect_ms + offset
                hold_dur = random.uniform(35, 80) / speed_multiplier  # Adjust hold dur for speed? Maybe, to feel natural
                release_time = press_time + hold_dur
                print(f"TAP PERFECT: {perfect_ms:.3f}ms | OFFSET: {offset:.3f}ms | PRESS: {press_time:.3f}ms | HOLD: {hold_dur:.3f}ms")

                events.append((press_time, 'down', key))
                events.append((release_time, 'up', key))

            elif ntype == "hold":
                st = (note.get("startTime") or 0) / speed_multiplier  # FIXED
                et = (note.get("endTime") or 0) / speed_multiplier  # FIXED
                start_off = self.get_offset(config["hold_start_low"], config["hold_start_high"], config["hold_start_bias"], config)
                end_off = self.get_offset(config["hold_end_low"], config["hold_end_high"], config["hold_end_bias"], config)
                print(f"HOLD START PERFECT: {st:.3f}ms | OFFSET: {start_off:.3f}ms | END PERFECT: {et:.3f}ms | OFFSET: {end_off:.3f}ms")
                events.append((st + start_off, 'down', key))
                events.append((et + end_off, 'up', key))

        events.sort(key=lambda e: e[0])

        # Group close events
        grouped_events = []
        current_group = []
        last_t = -9999

        for ev in events:
            t, act, k = ev
            if t - last_t < config["group_threshold"] / speed_multiplier and current_group:  # Adjust threshold for speed?
                current_group.append(ev)
            else:
                if current_group:
                    grouped_events.append((last_t, current_group))
                current_group = [ev]
                last_t = t
        if current_group:
            grouped_events.append((last_t, current_group))

        grouped_events.sort(key=lambda g: g[0])

        print(f"Total groups: {len(grouped_events)} 😈")

        self.sim_thread = threading.Thread(target=self._simulate_loop, args=(grouped_events, config), daemon=True)
        self.sim_thread.start()

        self.start_btn.config(text=f"Running... {mod} 😈")
        self.stop_btn.config(state="normal")
        self.stop_btn.pack(pady=5)

    def get_offset(self, low, high, bias, config):
        # NEW: Gaussian for human bell curve 💀😈 (clipped to range for hits)
        # Sigma set to (range)/4 for good spread without too much clipping
        range_val = high - low
        sigma = range_val / 4.0

        if random.random() < config["jump_prob"]:
            # Occasional jump: shift mu in dir, larger sigma, widened clip range
            dir = random.choice([-1, 1])
            shift = range_val / 2.0
            j_bias = bias + dir * shift
            j_sigma = sigma * config["jump_mult"]
            j_low = low * config["jump_mult"] if dir == -1 else low
            j_high = high * config["jump_mult"] if dir == 1 else high
            while True:
                offset = random.gauss(j_bias, j_sigma)
                if j_low <= offset <= j_high:
                    return offset
        else:
            while True:
                offset = random.gauss(bias, sigma)
                if low <= offset <= high:
                    return offset

    def wait_for_user_press(self, key):
        user_press_ms = [None]
        def listen():
            def on_press(pkey):
                try:
                    if hasattr(pkey, 'char') and pkey.char.lower() == key:
                        user_press_ms[0] = time.perf_counter() * 1000
                        print(f"User pressed '{key}' @ {user_press_ms[0]:.3f}ms 🔥")
                        return False
                except: pass

            tuner_listener = keyboard.Listener(on_press=on_press)
            tuner_listener.start()
            tuner_listener.join()

        threading.Thread(target=listen, daemon=True).start()
        start_wait = time.time()
        while user_press_ms[0] is None and self.running and time.time() - start_wait < 10:  # Longer timeout
            time.sleep(0.01)
        return user_press_ms[0]

    def update_timing_label(self):
        self.timing_label.config(text=f"Current Reference: Song Start @ {self.song_start_ms:.3f} ms | Offset Adj: {self.offset_adjust:.3f} ms")

    def periodic_update(self):
        if self.running:
            self.update_timing_label()
            self.root.after(1000, self.periodic_update)  # Every 1s

    def _simulate_loop(self, grouped_events, config):
        for perfect_t, group in grouped_events:
            if not self.running:
                break

            group_jitter = random.uniform(config["jitter_low"], config["jitter_high"])
            target_ms = self.song_start_ms + perfect_t + group_jitter
            now_ms = time.perf_counter() * 1000
            delay_s = max(0, (target_ms - now_ms) / 1000)

            if delay_s > 0:
                time.sleep(delay_s)

            if not self.running:
                break

            self._fire_group(group, perfect_t)

    def _fire_group(self, group, target_t):
        fire_ns = time.perf_counter_ns()
        fire_ms = fire_ns / 1_000_000
        sched_ms = self.song_start_ms + target_t
        delta_ms = fire_ms - sched_ms

        print(f"FIRE! GROUP @ ACTUAL: {fire_ms:.3f}ms (TARGET: {target_t:.3f}ms) | DELTA: {delta_ms:.3f}ms")

        random.shuffle(group)
        for sched_t, action, k in group:
            if not self.running:
                return
            act_ms = time.perf_counter_ns() / 1_000_000
            act_delta_ms = act_ms - (self.song_start_ms + sched_t)
            print(f"  ACTION '{action} {k}' @ {act_ms:.3f}ms (SCHED: {sched_t:.3f}ms) | DELTA: {act_delta_ms:.3f}ms")

            if action == 'down':
                if k not in self.currently_pressed:
                    self.kb.press(k)
                    self.currently_pressed.add(k)
            else:
                if k in self.currently_pressed:
                    self.kb.release(k)
                    self.currently_pressed.remove(k)

    def force_stop(self):
        print("FORCE STOPPING")
        self.running = False

        for k in list(self.currently_pressed):
            try:
                self.kb.release(k)
                print(f"Emergency release '{k}'")
            except:
                pass
        self.currently_pressed.clear()

        if self.is_windows:
            self.winmm.timeEndPeriod(1)
            print("Reset Windows Timer Resolution")

        self.reset_ui()

    def reset_ui(self):
        self.running = False
        self.start_btn.config(state="normal", text="Start Scanning", bg="red")
        self.stop_btn.config(state="disabled")
        self.stop_btn.pack_forget()
        self.import_btn.config(state="normal")
        if self.listener and self.listener.running:
            self.listener.stop()
            self.listener = None

    def cleanup(self):
        self.force_stop()
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RhythmCheatApp(root)
    root.mainloop()