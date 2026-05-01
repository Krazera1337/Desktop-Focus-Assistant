"""
config.py — User configuration with JSON persistence.

Settings are stored at ~/.focus_assistant/config.json so they survive restarts.
"""

import json
from pathlib import Path

CONFIG_DIR  = Path.home() / ".focus_assistant"
CONFIG_FILE = CONFIG_DIR  / "config.json"

DEFAULT_KEYWORDS = [
    "youtube", "reddit", "twitter", "x.com", "instagram", "facebook",
    "tiktok", "twitch", "netflix", "hulu", "disneyplus", "primevideo",
    "9gag", "imgur", "tumblr", "pinterest", "buzzfeed", "dailymail",
    "news.ycombinator",  # HN counts for some people
    "linkedin",          # remove if LinkedIn is work for you
]


class Config:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.distraction_keywords: list[str] = list(DEFAULT_KEYWORDS)
        self.threshold_minutes: int   = 10
        self.cooldown_minutes: int    = 5
        self.sound_enabled: bool      = True
        self.notification_enabled: bool = True
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.distraction_keywords  = data.get("distraction_keywords",
                                                       self.distraction_keywords)
                self.threshold_minutes     = data.get("threshold_minutes",
                                                       self.threshold_minutes)
                self.cooldown_minutes      = data.get("cooldown_minutes",
                                                       self.cooldown_minutes)
                self.sound_enabled         = data.get("sound_enabled",
                                                       self.sound_enabled)
                self.notification_enabled  = data.get("notification_enabled",
                                                       self.notification_enabled)
            except (json.JSONDecodeError, OSError):
                pass   # use defaults silently

    def save(self):
        data = {
            "distraction_keywords":  self.distraction_keywords,
            "threshold_minutes":     self.threshold_minutes,
            "cooldown_minutes":      self.cooldown_minutes,
            "sound_enabled":         self.sound_enabled,
            "notification_enabled":  self.notification_enabled,
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
