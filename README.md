# ◉ Focus Assistant

> A lightweight desktop productivity tool that monitors your active windows and nudges you back to work when you've spent too long on distraction sites.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![CI](https://img.shields.io/github/actions/workflow/status/yourusername/focus-assistant/ci.yml?style=flat-square&label=CI)

---

## Features

- **Cross-platform** — works on Windows, macOS, and Linux (X11)
- **Real-time window tracking** — polls your active window title every 2 seconds
- **Smart alerting** — fires a system notification + optional sound after a configurable threshold, with a cooldown to avoid spamming
- **Tkinter GUI** — live dashboard, per-window breakdown, editable distraction keyword list, settings panel
- **CLI / headless mode** — run without a display inside `tmux` or via cron
- **Persistent config** — settings survive restarts (`~/.focus_assistant/config.json`)
- **Zero heavy dependencies** — stdlib only for core functionality

---

## Screenshots

```
◉  FOCUS ASSISTANT                                              ● ACTIVE
────────────────────────────────────────────────────────────────────────
SESSION        FOCUS TIME      DISTRACTED      ALERTS SENT
01:23:44       01:10:02        00:13:42        2
────────────────────────────────────────────────────────────────────────
NOW   YouTube — Lo-Fi Beats to Study To              08:42 / 10:00 ⚠
```

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/yourusername/focus-assistant.git
cd focus-assistant

# No pip install required for core features — stdlib only!
# Optional: install pytest for tests
pip install pytest
```

### 2. Platform prerequisites

| OS | Requirement | Install |
|---|---|---|
| **Windows** | Nothing extra | — |
| **macOS** | Nothing extra (uses `osascript`) | — |
| **Linux** | `xdotool` for window detection | `sudo apt install xdotool libnotify-bin` |

### 3. Run the GUI

```bash
python focus_assistant.py
```

### 4. Run headless (CLI mode)

```bash
python cli.py
python cli.py --threshold 5 --cooldown 2 --interval 10
```

---

## Project Structure

```
focus-assistant/
├── focus_assistant.py   # Tkinter GUI — main entry point
├── tracker.py           # Window polling + time accumulation logic
├── notifier.py          # Cross-platform OS notifications + sound
├── config.py            # JSON-backed settings (~/.focus_assistant/)
├── cli.py               # Headless terminal mode
├── requirements.txt     # Optional dependencies
├── tests/
│   └── test_focus_assistant.py   # pytest suite
└── .github/
    └── workflows/
        └── ci.yml       # GitHub Actions CI (Win / macOS / Linux)
```

---

## Configuration

Settings are stored at `~/.focus_assistant/config.json` and editable in the GUI's Settings tab.

| Setting | Default | Description |
|---|---|---|
| `threshold_minutes` | `10` | Minutes on a distraction site before alert fires |
| `cooldown_minutes` | `5` | Minimum gap between alerts for the same window |
| `sound_enabled` | `true` | Play a beep when alerting |
| `notification_enabled` | `true` | Send an OS toast notification |
| `distraction_keywords` | *(see below)* | Case-insensitive window-title substrings |

Default distraction keywords: `youtube, reddit, twitter, instagram, facebook, tiktok, twitch, netflix, hulu, 9gag, imgur, tumblr, pinterest, buzzfeed, dailymail, linkedin`

Edit them any time in the **Distractions** tab — changes apply immediately.

---

## How It Works

```
Background thread (every 2s)
    │
    ▼
_get_active_window_title()    ← xdotool / osascript / WinAPI
    │
    ▼
Is title a distraction?       ← keyword substring match
    │ yes
    ▼
seconds ≥ threshold?
    │ yes
    ▼
cooldown elapsed?             ← per-window timestamp check
    │ yes
    ▼
notifier.send(alert)          ← OS toast + optional beep
```

The UI thread refreshes every 2 seconds from the same `tracker.get_stats()` snapshot — no shared mutable state, thread-safe by design.

---

## Running Tests

```bash
pytest tests/ -v

# Linux CI uses xvfb for a virtual display:
xvfb-run --auto-servernum pytest tests/ -v
```

The test suite covers:
- Config save / reload / corruption handling
- Distraction keyword matching (case-insensitive)
- Alert threshold and cooldown logic
- Session reset
- Window-switch time commitment
- `get_stats()` return shape

---

## Optional: Windows Toast Notifications

For richer Windows toasts, install `win10toast`:

```bash
pip install win10toast
```

Without it, the app falls back to a PowerShell balloon tip (no extra install needed).

---

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b feature/my-feature`
3. Make your changes + add tests
4. Run `pytest tests/ -v` — all green
5. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE) for details.
