"""
focus_assistant.py — Desktop Focus Assistant
Monitors active windows and alerts you when you've spent too long on distractions.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import sys
import platform
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from tracker import WindowTracker
from notifier import Notifier
from config import Config


class FocusApp:
    """Main GUI application for the Focus Assistant."""

    APP_NAME = "Focus Assistant"
    POLL_INTERVAL_MS = 2000       # UI refresh rate
    TRACKER_INTERVAL_SEC = 2      # background polling rate

    # ── colour palette ──────────────────────────────────────────────────────
    BG          = "#0f0f11"
    SURFACE     = "#1a1a1f"
    SURFACE2    = "#22222a"
    BORDER      = "#2e2e38"
    ACCENT      = "#6366f1"       # indigo
    ACCENT_DIM  = "#3730a3"
    WARN        = "#f59e0b"
    DANGER      = "#ef4444"
    SUCCESS     = "#10b981"
    TEXT        = "#f1f0ee"
    TEXT_MID    = "#9998a0"
    TEXT_DIM    = "#55545f"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = Config()
        self.tracker = WindowTracker(self.config)
        self.notifier = Notifier(self.config)

        self._running = False
        self._bg_thread: threading.Thread | None = None
        self._session_start = datetime.now()

        self._build_ui()
        self._apply_theme()
        self._start_tracking()
        self._schedule_refresh()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.title(self.APP_NAME)
        self.root.geometry("780x620")
        self.root.minsize(680, 540)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.BG, pady=0)
        hdr.pack(fill="x", padx=24, pady=(22, 0))

        tk.Label(hdr, text="◉  FOCUS ASSISTANT",
                 bg=self.BG, fg=self.ACCENT,
                 font=("Courier New", 13, "bold")).pack(side="left")

        self._status_dot = tk.Label(hdr, text="●", bg=self.BG,
                                    fg=self.SUCCESS, font=("Courier New", 16))
        self._status_dot.pack(side="right", padx=(0, 4))
        tk.Label(hdr, text="ACTIVE", bg=self.BG, fg=self.TEXT_MID,
                 font=("Courier New", 10)).pack(side="right")

        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill="x", padx=24, pady=14)

        # ── stat strip ──────────────────────────────────────────────────────
        stats_row = tk.Frame(self.root, bg=self.BG)
        stats_row.pack(fill="x", padx=24, pady=(0, 16))

        self._stat_session = self._stat_card(stats_row, "SESSION", "00:00:00")
        self._stat_focus   = self._stat_card(stats_row, "FOCUS TIME", "00:00:00")
        self._stat_lost    = self._stat_card(stats_row, "DISTRACTED", "00:00:00")
        self._stat_alerts  = self._stat_card(stats_row, "ALERTS SENT", "0")

        # ── current window strip ─────────────────────────────────────────────
        cur = tk.Frame(self.root, bg=self.SURFACE, padx=16, pady=10)
        cur.pack(fill="x", padx=24, pady=(0, 14))

        tk.Label(cur, text="NOW  ", bg=self.SURFACE, fg=self.TEXT_DIM,
                 font=("Courier New", 9)).pack(side="left")
        self._cur_label = tk.Label(cur, text="—", bg=self.SURFACE,
                                   fg=self.TEXT, font=("Courier New", 11, "bold"),
                                   anchor="w")
        self._cur_label.pack(side="left", fill="x", expand=True)
        self._cur_timer = tk.Label(cur, text="", bg=self.SURFACE,
                                   fg=self.WARN, font=("Courier New", 11, "bold"))
        self._cur_timer.pack(side="right")

        # ── notebook / tabs ──────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.TNotebook",
                        background=self.BG, borderwidth=0, tabmargins=0)
        style.configure("Custom.TNotebook.Tab",
                        background=self.SURFACE2, foreground=self.TEXT_MID,
                        padding=[16, 7], font=("Courier New", 9, "bold"),
                        borderwidth=0)
        style.map("Custom.TNotebook.Tab",
                  background=[("selected", self.SURFACE)],
                  foreground=[("selected", self.ACCENT)])

        nb = ttk.Notebook(self.root, style="Custom.TNotebook")
        nb.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._tab_dashboard = tk.Frame(nb, bg=self.SURFACE)
        self._tab_sites     = tk.Frame(nb, bg=self.SURFACE)
        self._tab_settings  = tk.Frame(nb, bg=self.SURFACE)

        nb.add(self._tab_dashboard, text=" DASHBOARD ")
        nb.add(self._tab_sites,     text=" DISTRACTIONS ")
        nb.add(self._tab_settings,  text=" SETTINGS ")

        self._build_dashboard_tab()
        self._build_sites_tab()
        self._build_settings_tab()

        # ── footer ───────────────────────────────────────────────────────────
        ft = tk.Frame(self.root, bg=self.BG)
        ft.pack(fill="x", padx=24, pady=(0, 14))

        self._toggle_btn = tk.Button(ft, text="⏸  PAUSE",
                                     command=self._toggle_tracking,
                                     bg=self.ACCENT, fg=self.TEXT,
                                     font=("Courier New", 10, "bold"),
                                     relief="flat", padx=18, pady=6,
                                     cursor="hand2", activebackground=self.ACCENT_DIM,
                                     activeforeground=self.TEXT, bd=0)
        self._toggle_btn.pack(side="left")

        tk.Button(ft, text="↺  RESET SESSION",
                  command=self._reset_session,
                  bg=self.SURFACE2, fg=self.TEXT_MID,
                  font=("Courier New", 10), relief="flat",
                  padx=14, pady=6, cursor="hand2",
                  activebackground=self.BORDER,
                  activeforeground=self.TEXT, bd=0).pack(side="left", padx=8)

        self._last_alert_label = tk.Label(ft, text="",
                                          bg=self.BG, fg=self.TEXT_DIM,
                                          font=("Courier New", 9))
        self._last_alert_label.pack(side="right")

    def _stat_card(self, parent, label, value):
        frame = tk.Frame(parent, bg=self.SURFACE2, padx=18, pady=12)
        frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(frame, text=label, bg=self.SURFACE2,
                 fg=self.TEXT_DIM, font=("Courier New", 8)).pack(anchor="w")
        val = tk.Label(frame, text=value, bg=self.SURFACE2,
                       fg=self.TEXT, font=("Courier New", 18, "bold"))
        val.pack(anchor="w")
        return val

    def _build_dashboard_tab(self):
        tab = self._tab_dashboard
        tk.Label(tab, text="TOP WINDOWS TODAY",
                 bg=self.SURFACE, fg=self.TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(14, 6))

        cols = ("Window / Site", "Time Spent", "Type", "Alerts")
        self._tree = ttk.Treeview(tab, columns=cols, show="headings",
                                   height=10, selectmode="none")
        style = ttk.Style()
        style.configure("Treeview",
                        background=self.SURFACE, foreground=self.TEXT,
                        fieldbackground=self.SURFACE, rowheight=32,
                        borderwidth=0, font=("Courier New", 10))
        style.configure("Treeview.Heading",
                        background=self.SURFACE2, foreground=self.TEXT_MID,
                        font=("Courier New", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", self.ACCENT_DIM)])

        widths = [320, 110, 90, 70]
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w" if w > 100 else "center",
                               minwidth=60)

        self._tree.tag_configure("distraction", foreground=self.WARN)
        self._tree.tag_configure("focus",       foreground=self.SUCCESS)
        self._tree.tag_configure("neutral",     foreground=self.TEXT_MID)

        sb = ttk.Scrollbar(tab, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=(0, 14))
        sb.pack(side="left", fill="y", pady=(0, 14))

    def _build_sites_tab(self):
        tab = self._tab_sites
        tk.Label(tab, text="DISTRACTION KEYWORDS  (one per line, case-insensitive)",
                 bg=self.SURFACE, fg=self.TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(14, 6))

        self._sites_text = tk.Text(tab, bg=self.SURFACE2, fg=self.TEXT,
                                    insertbackground=self.TEXT,
                                    font=("Courier New", 11),
                                    relief="flat", padx=12, pady=10,
                                    selectbackground=self.ACCENT_DIM,
                                    width=40, height=16,
                                    highlightthickness=1,
                                    highlightcolor=self.BORDER,
                                    highlightbackground=self.BORDER)
        self._sites_text.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self._sites_text.insert("1.0", "\n".join(self.config.distraction_keywords))

        btn_row = tk.Frame(tab, bg=self.SURFACE)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(btn_row, text="SAVE LIST",
                  command=self._save_keywords,
                  bg=self.ACCENT, fg=self.TEXT,
                  font=("Courier New", 10, "bold"),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2", activebackground=self.ACCENT_DIM,
                  activeforeground=self.TEXT, bd=0).pack(side="left")
        self._kw_saved = tk.Label(btn_row, text="", bg=self.SURFACE,
                                   fg=self.SUCCESS, font=("Courier New", 9))
        self._kw_saved.pack(side="left", padx=10)

    def _build_settings_tab(self):
        tab = self._tab_settings

        def row(label, var, suffix=""):
            f = tk.Frame(tab, bg=self.SURFACE)
            f.pack(fill="x", padx=16, pady=6)
            tk.Label(f, text=label, bg=self.SURFACE, fg=self.TEXT_MID,
                     font=("Courier New", 10), width=30, anchor="w").pack(side="left")
            e = tk.Entry(f, textvariable=var, bg=self.SURFACE2, fg=self.TEXT,
                         insertbackground=self.TEXT, font=("Courier New", 11),
                         relief="flat", width=8,
                         highlightthickness=1,
                         highlightcolor=self.BORDER,
                         highlightbackground=self.BORDER)
            e.pack(side="left")
            if suffix:
                tk.Label(f, text=f"  {suffix}", bg=self.SURFACE,
                         fg=self.TEXT_DIM, font=("Courier New", 9)).pack(side="left")

        tk.Label(tab, text="ALERT SETTINGS",
                 bg=self.SURFACE, fg=self.TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(14, 8))

        self._var_threshold = tk.StringVar(value=str(self.config.threshold_minutes))
        self._var_cooldown  = tk.StringVar(value=str(self.config.cooldown_minutes))
        self._var_sound_en  = tk.BooleanVar(value=self.config.sound_enabled)
        self._var_notif_en  = tk.BooleanVar(value=self.config.notification_enabled)

        row("Alert threshold", self._var_threshold, "minutes on distraction site")
        row("Cooldown between alerts", self._var_cooldown, "minutes")

        tk.Frame(tab, bg=self.BORDER, height=1).pack(fill="x", padx=16, pady=12)
        tk.Label(tab, text="NOTIFICATION METHODS",
                 bg=self.SURFACE, fg=self.TEXT_DIM,
                 font=("Courier New", 9)).pack(anchor="w", padx=16, pady=(0, 8))

        def check_row(label, var):
            f = tk.Frame(tab, bg=self.SURFACE)
            f.pack(fill="x", padx=16, pady=4)
            tk.Checkbutton(f, text=label, variable=var,
                           bg=self.SURFACE, fg=self.TEXT,
                           activebackground=self.SURFACE,
                           activeforeground=self.ACCENT,
                           selectcolor=self.SURFACE2,
                           font=("Courier New", 10),
                           cursor="hand2").pack(side="left")

        check_row("System notification (OS toast)", self._var_notif_en)
        check_row("Sound alert (beep)",              self._var_sound_en)

        tk.Frame(tab, bg=self.BORDER, height=1).pack(fill="x", padx=16, pady=12)
        tk.Button(tab, text="SAVE SETTINGS",
                  command=self._save_settings,
                  bg=self.ACCENT, fg=self.TEXT,
                  font=("Courier New", 10, "bold"),
                  relief="flat", padx=14, pady=5,
                  cursor="hand2", activebackground=self.ACCENT_DIM,
                  activeforeground=self.TEXT, bd=0).pack(anchor="w", padx=16)

        self._settings_saved = tk.Label(tab, text="", bg=self.SURFACE,
                                         fg=self.SUCCESS, font=("Courier New", 9))
        self._settings_saved.pack(anchor="w", padx=16, pady=4)

    def _apply_theme(self):
        """Additional theming after widget construction."""
        self.root.configure(bg=self.BG)

    # ── tracking ─────────────────────────────────────────────────────────────

    def _start_tracking(self):
        self._running = True
        self._bg_thread = threading.Thread(target=self._bg_loop, daemon=True)
        self._bg_thread.start()

    def _bg_loop(self):
        while self._running:
            try:
                alert = self.tracker.tick()
                if alert:
                    self.notifier.send(alert)
            except Exception as e:
                print(f"[tracker] error: {e}")
            time.sleep(self.TRACKER_INTERVAL_SEC)

    def _toggle_tracking(self):
        if self._running:
            self._running = False
            self._toggle_btn.config(text="▶  RESUME", bg=self.WARN)
            self._status_dot.config(fg=self.WARN)
        else:
            self._running = True
            self._start_tracking()
            self._toggle_btn.config(text="⏸  PAUSE", bg=self.ACCENT)
            self._status_dot.config(fg=self.SUCCESS)

    def _reset_session(self):
        if messagebox.askyesno("Reset", "Reset all session data?",
                               icon="warning"):
            self.tracker.reset()
            self._session_start = datetime.now()

    # ── UI refresh ────────────────────────────────────────────────────────────

    def _schedule_refresh(self):
        self._refresh_ui()
        self.root.after(self.POLL_INTERVAL_MS, self._schedule_refresh)

    def _refresh_ui(self):
        data = self.tracker.get_stats()

        # stat strip
        session_dur = datetime.now() - self._session_start
        self._stat_session.config(text=self._fmt_dur(session_dur.total_seconds()))
        self._stat_focus.config(text=self._fmt_dur(data["focus_seconds"]))
        self._stat_lost.config(text=self._fmt_dur(data["distraction_seconds"]),
                                fg=self.DANGER if data["distraction_seconds"] > 0 else self.TEXT)
        self._stat_alerts.config(text=str(data["alert_count"]))

        # current window
        cur = data.get("current_window", "")
        is_dist = data.get("current_is_distraction", False)
        cur_secs = data.get("current_window_seconds", 0)
        self._cur_label.config(text=cur[:72] if cur else "—",
                                fg=self.WARN if is_dist else self.TEXT)
        if is_dist and cur_secs > 0:
            threshold_s = self.config.threshold_minutes * 60
            self._cur_timer.config(
                text=f"{self._fmt_dur(cur_secs)} / {self._fmt_dur(threshold_s)}",
                fg=self.DANGER if cur_secs >= threshold_s else self.WARN)
        else:
            self._cur_timer.config(text="")

        # last alert
        la = data.get("last_alert")
        if la:
            self._last_alert_label.config(text=f"Last alert: {la}")

        # treeview
        for row in self._tree.get_children():
            self._tree.delete(row)
        for entry in sorted(data["window_log"].items(),
                            key=lambda x: x[1]["seconds"], reverse=True)[:20]:
            name, info = entry
            tag = "distraction" if info["distraction"] else (
                  "focus" if info["seconds"] > 120 else "neutral")
            self._tree.insert("", "end",
                values=(
                    name[:60],
                    self._fmt_dur(info["seconds"]),
                    "⚠ distraction" if info["distraction"] else "✓ focus",
                    str(info.get("alert_count", 0))
                ),
                tags=(tag,))

    @staticmethod
    def _fmt_dur(seconds: float) -> str:
        s = int(seconds)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    # ── actions ───────────────────────────────────────────────────────────────

    def _save_keywords(self):
        raw = self._sites_text.get("1.0", "end").strip()
        kws = [k.strip().lower() for k in raw.splitlines() if k.strip()]
        self.config.distraction_keywords = kws
        self.config.save()
        self.tracker.reload_config()
        self._kw_saved.config(text="✓ Saved")
        self.root.after(2000, lambda: self._kw_saved.config(text=""))

    def _save_settings(self):
        try:
            self.config.threshold_minutes   = int(self._var_threshold.get())
            self.config.cooldown_minutes    = int(self._var_cooldown.get())
            self.config.sound_enabled       = self._var_sound_en.get()
            self.config.notification_enabled = self._var_notif_en.get()
            self.config.save()
            self.tracker.reload_config()
            self._settings_saved.config(text="✓ Saved")
            self.root.after(2000, lambda: self._settings_saved.config(text=""))
        except ValueError:
            messagebox.showerror("Invalid", "Threshold and cooldown must be whole numbers.")

    def _on_close(self):
        self._running = False
        self.root.destroy()


def main():
    root = tk.Tk()
    app = FocusApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
