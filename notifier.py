"""
notifier.py — Cross-platform system notifications and sound alerts.

Supports:
  - Windows  : win10toast (toast notifications) + winsound beep
  - macOS    : osascript display notification + NSBeep / afplay
  - Linux    : notify-send + paplay / beep command
"""

import platform
import subprocess
import threading
from config import Config

SYSTEM = platform.system()


def _notify_windows(title: str, message: str):
    try:
        from win10toast import ToastNotifier   # type: ignore
        ToastNotifier().show_toast(
            title, message,
            duration=8, threaded=True,
            icon_path=None
        )
    except ImportError:
        # Fallback: PowerShell balloon tip (no extra dependencies)
        ps = (
            f'Add-Type -AssemblyName System.Windows.Forms;'
            f'$n = New-Object System.Windows.Forms.NotifyIcon;'
            f'$n.Icon = [System.Drawing.SystemIcons]::Information;'
            f'$n.Visible = $true;'
            f'$n.ShowBalloonTip(8000, "{title}", "{message}", '
            f'[System.Windows.Forms.ToolTipIcon]::Warning);'
            f'Start-Sleep -Seconds 10; $n.Dispose()'
        )
        subprocess.Popen(
            ["powershell", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW   # type: ignore[attr-defined]
        )


def _notify_macos(title: str, message: str):
    script = f'display notification "{message}" with title "{title}" sound name "Frog"'
    subprocess.run(["osascript", "-e", script],
                   capture_output=True, timeout=5)


def _notify_linux(title: str, message: str):
    subprocess.run(
        ["notify-send", "--urgency=normal", "--expire-time=8000",
         "--app-name=Focus Assistant", title, message],
        capture_output=True, timeout=5
    )


def _play_sound_windows():
    try:
        import winsound                  # type: ignore
        for _ in range(3):
            winsound.Beep(880, 300)
    except Exception:
        pass


def _play_sound_macos():
    subprocess.run(["afplay", "/System/Library/Sounds/Funk.aiff"],
                   capture_output=True, timeout=5)


def _play_sound_linux():
    # Try paplay, then aplay, then the console beep
    for cmd in [
        ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
        ["aplay",  "/usr/share/sounds/alsa/Front_Right.wav"],
        ["beep",   "-f", "880", "-l", "300", "-r", "3"],
    ]:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        if result.returncode == 0:
            return
    # Last resort: BEL character to terminal
    print("\a\a\a", end="", flush=True)


class Notifier:
    """Dispatches system notifications and/or sound alerts on a daemon thread."""

    TITLE = "Focus Assistant 🎯"

    def __init__(self, config: Config):
        self.config = config

    def send(self, message: str):
        """Non-blocking: fire notification in a daemon thread."""
        t = threading.Thread(target=self._dispatch, args=(message,), daemon=True)
        t.start()

    def _dispatch(self, message: str):
        if self.config.notification_enabled:
            try:
                self._os_notify(message)
            except Exception as e:
                print(f"[notifier] notification error: {e}")

        if self.config.sound_enabled:
            try:
                self._os_sound()
            except Exception as e:
                print(f"[notifier] sound error: {e}")

    def _os_notify(self, message: str):
        if SYSTEM == "Windows":
            _notify_windows(self.TITLE, message)
        elif SYSTEM == "Darwin":
            _notify_macos(self.TITLE, message)
        else:
            _notify_linux(self.TITLE, message)

    def _os_sound(self):
        if SYSTEM == "Windows":
            _play_sound_windows()
        elif SYSTEM == "Darwin":
            _play_sound_macos()
        else:
            _play_sound_linux()
