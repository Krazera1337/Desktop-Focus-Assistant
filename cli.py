"""
cli.py — Headless CLI mode for Focus Assistant.

Run this on systems without a display, inside tmux/screen, or via cron.

Usage:
    python cli.py
    python cli.py --threshold 5 --cooldown 3
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from config import Config
from tracker import WindowTracker
from notifier import Notifier

RESET   = "\033[0m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
GREEN   = "\033[92m"
CYAN    = "\033[96m"
DIM     = "\033[2m"
BOLD    = "\033[1m"


def fmt_dur(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:02d}h {m:02d}m {sec:02d}s"
    return f"{m:02d}m {sec:02d}s"


def main():
    parser = argparse.ArgumentParser(
        description="Focus Assistant — headless CLI mode",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--threshold", type=int,
                        help="Alert after N minutes on distraction site")
    parser.add_argument("--cooldown",  type=int,
                        help="Minimum minutes between alerts for the same site")
    parser.add_argument("--interval",  type=int, default=5,
                        help="Status print interval in seconds")
    args = parser.parse_args()

    cfg = Config()
    if args.threshold: cfg.threshold_minutes = args.threshold
    if args.cooldown:  cfg.cooldown_minutes  = args.cooldown

    tracker  = WindowTracker(cfg)
    notifier = Notifier(cfg)

    print(f"\n{BOLD}◉  Focus Assistant — CLI mode{RESET}")
    print(f"{DIM}Threshold : {cfg.threshold_minutes} min  |  "
          f"Cooldown : {cfg.cooldown_minutes} min{RESET}")
    print(f"{DIM}Distraction keywords: {', '.join(cfg.distraction_keywords[:5])} …{RESET}")
    print(f"{DIM}Press Ctrl-C to exit.{RESET}\n")

    def _shutdown(sig, frame):
        stats = tracker.get_stats()
        print(f"\n{BOLD}Session summary{RESET}")
        print(f"  Focus time     : {GREEN}{fmt_dur(stats['focus_seconds'])}{RESET}")
        print(f"  Distracted time: {RED}{fmt_dur(stats['distraction_seconds'])}{RESET}")
        print(f"  Alerts fired   : {stats['alert_count']}")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    tick = 0
    while True:
        alert = tracker.tick()
        if alert:
            print(f"\n{YELLOW}{BOLD}[ALERT]{RESET} {alert}")
            notifier.send(alert)

        tick += 1
        if tick % (args.interval // 2 or 1) == 0:
            stats  = tracker.get_stats()
            cur    = stats["current_window"] or "—"
            colour = RED if stats["current_is_distraction"] else GREEN
            ts     = datetime.now().strftime("%H:%M:%S")
            print(
                f"{DIM}{ts}{RESET}  "
                f"{colour}{cur[:55]:<55}{RESET}  "
                f"F {GREEN}{fmt_dur(stats['focus_seconds'])}{RESET}  "
                f"D {RED}{fmt_dur(stats['distraction_seconds'])}{RESET}",
                end="\r", flush=True
            )

        time.sleep(2)


if __name__ == "__main__":
    main()
