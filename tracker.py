"""
tracker.py — Cross-platform active window tracker.

Detects the current foreground window title and accumulates time per window.
Fires an alert when a distraction site exceeds the configured threshold.
"""

import platform
import time
from datetime import datetime
from typing import Optional
from config import Config


def _get_active_window_title() -> str:
    """Return the title of the currently focused window (cross-platform)."""
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or ""
        except Exception:
            return ""

    elif system == "Darwin":  # macOS
        try:
            from AppKit import NSWorkspace  # type: ignore
            app = NSWorkspace.sharedWorkspace().activeApplication()
            return app.get("NSApplicationName", "") if app else ""
        except ImportError:
            # Fallback: use osascript
            import subprocess
            script = (
                'tell application "System Events" to get name of '
                'first application process whose frontmost is true'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip()

    else:  # Linux (X11)
        try:
            import subprocess
            # Try xdotool first (most reliable)
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout.strip()
            # Fallback: wmctrl
            result = subprocess.run(
                ["wmctrl", "-a", ":ACTIVE:"],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip()
        except Exception:
            return ""


class WindowStats:
    """Accumulates time and alert count for a single window/title."""
    __slots__ = ("seconds", "distraction", "alert_count", "last_seen")

    def __init__(self, distraction: bool):
        self.seconds: float = 0.0
        self.distraction: bool = distraction
        self.alert_count: int = 0
        self.last_seen: datetime = datetime.now()

    def to_dict(self):
        return {
            "seconds": self.seconds,
            "distraction": self.distraction,
            "alert_count": self.alert_count,
        }


class WindowTracker:
    """
    Polls the active window at a fixed cadence and accumulates statistics.

    Alert logic:
      - A window is a "distraction" if any keyword from config appears in its
        title (case-insensitive).
      - Once a distraction window has been active for >= threshold_minutes,
        an alert is triggered.
      - Subsequent alerts for the *same* window are suppressed until the
        cooldown_minutes have elapsed.
    """

    def __init__(self, config: Config):
        self.config = config
        self._reset_state()

    def _reset_state(self):
        self._window_log: dict[str, WindowStats] = {}
        self._current_window: str = ""
        self._current_start: float = time.monotonic()
        self._focus_seconds: float = 0.0
        self._distraction_seconds: float = 0.0
        self._alert_count: int = 0
        self._last_alert_time: Optional[float] = None   # monotonic
        self._last_alert_label: str = ""
        # Per-window last-alert timestamp (to enforce per-window cooldown)
        self._window_last_alert: dict[str, float] = {}

    def reset(self):
        self._reset_state()

    def reload_config(self):
        """Call after config changes to pick up new keywords / thresholds."""
        # Re-evaluate distraction flag for all known windows
        for title, stats in self._window_log.items():
            stats.distraction = self._is_distraction(title)

    # ── core ─────────────────────────────────────────────────────────────────

    def tick(self) -> Optional[str]:
        """
        Called periodically by the background thread.
        Returns an alert message string if the threshold was crossed,
        or None if no alert should fire.
        """
        title = _get_active_window_title()
        now   = time.monotonic()
        elapsed = now - self._current_start

        if title != self._current_window:
            # Commit elapsed time to the previous window
            self._commit(self._current_window, elapsed)
            self._current_window = title
            self._current_start  = now
        else:
            # Accumulate into current window stats
            self._commit(title, elapsed, update_start=True)

        # Check for alert
        if title and self._is_distraction(title):
            stats = self._window_log.get(title)
            if stats and stats.seconds >= self.config.threshold_minutes * 60:
                return self._maybe_alert(title, stats, now)
        return None

    def _commit(self, title: str, elapsed: float, update_start: bool = False):
        if not title:
            return
        distraction = self._is_distraction(title)
        if title not in self._window_log:
            self._window_log[title] = WindowStats(distraction)

        stats = self._window_log[title]
        stats.seconds   += elapsed
        stats.last_seen  = datetime.now()
        stats.distraction = distraction   # refresh in case keywords changed

        if distraction:
            self._distraction_seconds += elapsed
        else:
            self._focus_seconds += elapsed

        if update_start:
            self._current_start = time.monotonic()

    def _is_distraction(self, title: str) -> bool:
        low = title.lower()
        return any(kw in low for kw in self.config.distraction_keywords)

    def _maybe_alert(self, title: str, stats: WindowStats, now: float) -> Optional[str]:
        """Return an alert message if cooldown has expired, else None."""
        last = self._window_last_alert.get(title)
        cooldown_s = self.config.cooldown_minutes * 60

        if last is None or (now - last) >= cooldown_s:
            stats.alert_count            += 1
            self._alert_count            += 1
            self._window_last_alert[title] = now
            self._last_alert_label = datetime.now().strftime("%H:%M:%S")

            mins = int(stats.seconds // 60)
            return (
                f"You've been on '{self._short(title)}' for {mins} minute(s).\n"
                f"Time to refocus! 🎯"
            )
        return None

    @staticmethod
    def _short(title: str, max_len: int = 40) -> str:
        return title[:max_len] + "…" if len(title) > max_len else title

    # ── stats for UI ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        cur = self._current_window
        cur_elapsed = time.monotonic() - self._current_start
        cur_stats = self._window_log.get(cur)

        return {
            "focus_seconds":         self._focus_seconds,
            "distraction_seconds":   self._distraction_seconds,
            "alert_count":           self._alert_count,
            "current_window":        cur,
            "current_is_distraction": self._is_distraction(cur) if cur else False,
            "current_window_seconds": (cur_stats.seconds if cur_stats else 0) + cur_elapsed,
            "window_log":            {k: v.to_dict() for k, v in self._window_log.items()},
            "last_alert":            self._last_alert_label or None,
        }
