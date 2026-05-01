"""
tests/test_focus_assistant.py — Unit tests for Focus Assistant.

Run with:  pytest tests/ -v
"""

import pytest
import time
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import Config
from tracker import WindowTracker, WindowStats


# ── Config ────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config.CONFIG_DIR",  tmp_path)
        monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
        cfg = Config()
        assert cfg.threshold_minutes == 10
        assert cfg.cooldown_minutes  == 5
        assert "youtube" in cfg.distraction_keywords

    def test_save_and_reload(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config.CONFIG_DIR",  tmp_path)
        cf = tmp_path / "config.json"
        monkeypatch.setattr("config.CONFIG_FILE", cf)
        cfg = Config()
        cfg.threshold_minutes = 3
        cfg.distraction_keywords = ["test_site"]
        cfg.save()

        cfg2 = Config()
        assert cfg2.threshold_minutes == 3
        assert "test_site" in cfg2.distraction_keywords

    def test_corrupted_file_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config.CONFIG_DIR",  tmp_path)
        cf = tmp_path / "config.json"
        cf.write_text("NOT JSON {{{{", encoding="utf-8")
        monkeypatch.setattr("config.CONFIG_FILE", cf)
        cfg = Config()
        assert cfg.threshold_minutes == 10   # default restored


# ── WindowStats ───────────────────────────────────────────────────────────────

class TestWindowStats:
    def test_initial_values(self):
        ws = WindowStats(distraction=True)
        assert ws.seconds      == 0.0
        assert ws.distraction  is True
        assert ws.alert_count  == 0

    def test_to_dict(self):
        ws = WindowStats(distraction=False)
        ws.seconds     = 42.5
        ws.alert_count = 1
        d = ws.to_dict()
        assert d["seconds"]     == 42.5
        assert d["distraction"] is False
        assert d["alert_count"] == 1


# ── WindowTracker ─────────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_DIR",  tmp_path)
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    c = Config()
    c.threshold_minutes = 1       # short threshold for tests
    c.cooldown_minutes  = 1
    c.distraction_keywords = ["youtube", "reddit"]
    return c


class TestWindowTracker:
    def test_is_distraction_match(self, cfg):
        tracker = WindowTracker(cfg)
        assert tracker._is_distraction("YouTube — My Video") is True
        assert tracker._is_distraction("reddit - Python")    is True

    def test_is_distraction_no_match(self, cfg):
        tracker = WindowTracker(cfg)
        assert tracker._is_distraction("VS Code — main.py")  is False
        assert tracker._is_distraction("")                    is False

    def test_case_insensitive(self, cfg):
        tracker = WindowTracker(cfg)
        assert tracker._is_distraction("YOUTUBE.COM")         is True
        assert tracker._is_distraction("YouTube Music")       is True

    @patch("tracker._get_active_window_title")
    def test_tick_accumulates_time(self, mock_win, cfg):
        mock_win.return_value = "VS Code — main.py"
        tracker = WindowTracker(cfg)
        for _ in range(5):
            tracker.tick()
            time.sleep(0.05)
        stats = tracker.get_stats()
        assert stats["focus_seconds"] > 0

    @patch("tracker._get_active_window_title")
    def test_alert_fires_after_threshold(self, mock_win, cfg):
        cfg.threshold_minutes = 0   # fire immediately
        mock_win.return_value = "YouTube — Cats Compilation"
        tracker = WindowTracker(cfg)

        # Manually push the stats over threshold
        tracker._window_log["YouTube — Cats Compilation"] = WindowStats(True)
        tracker._window_log["YouTube — Cats Compilation"].seconds = 61
        tracker._current_window = "YouTube — Cats Compilation"

        alert = tracker._maybe_alert(
            "YouTube — Cats Compilation",
            tracker._window_log["YouTube — Cats Compilation"],
            time.monotonic()
        )
        assert alert is not None
        assert "YouTube" in alert

    @patch("tracker._get_active_window_title")
    def test_cooldown_suppresses_duplicate_alerts(self, mock_win, cfg):
        cfg.threshold_minutes = 0
        cfg.cooldown_minutes  = 60   # very long cooldown
        mock_win.return_value = "reddit — Python"
        tracker = WindowTracker(cfg)

        tracker._window_log["reddit — Python"] = WindowStats(True)
        tracker._window_log["reddit — Python"].seconds = 999
        tracker._current_window = "reddit — Python"

        now = time.monotonic()
        first  = tracker._maybe_alert("reddit — Python",
                                       tracker._window_log["reddit — Python"], now)
        second = tracker._maybe_alert("reddit — Python",
                                       tracker._window_log["reddit — Python"], now + 5)
        assert first  is not None
        assert second is None   # suppressed by cooldown

    @patch("tracker._get_active_window_title")
    def test_reset_clears_stats(self, mock_win, cfg):
        mock_win.return_value = "YouTube — test"
        tracker = WindowTracker(cfg)
        for _ in range(3):
            tracker.tick()
        tracker.reset()
        stats = tracker.get_stats()
        assert stats["focus_seconds"]       == 0
        assert stats["distraction_seconds"] == 0
        assert stats["alert_count"]         == 0

    @patch("tracker._get_active_window_title")
    def test_get_stats_structure(self, mock_win, cfg):
        mock_win.return_value = "VS Code"
        tracker = WindowTracker(cfg)
        tracker.tick()
        stats = tracker.get_stats()
        expected_keys = {
            "focus_seconds", "distraction_seconds", "alert_count",
            "current_window", "current_is_distraction",
            "current_window_seconds", "window_log", "last_alert"
        }
        assert expected_keys.issubset(stats.keys())

    def test_reload_config_updates_distraction_flags(self, cfg):
        tracker = WindowTracker(cfg)
        tracker._window_log["HackerNews"] = WindowStats(False)
        cfg.distraction_keywords.append("hackernews")
        tracker.reload_config()
        assert tracker._window_log["HackerNews"].distraction is True


# ── Integration ───────────────────────────────────────────────────────────────

class TestIntegration:
    @patch("tracker._get_active_window_title")
    def test_window_switch_commits_time(self, mock_win, cfg):
        tracker = WindowTracker(cfg)

        mock_win.return_value = "VS Code"
        tracker.tick()
        time.sleep(0.1)

        mock_win.return_value = "YouTube — video"
        tracker.tick()           # switches window → commits VS Code time

        stats = tracker.get_stats()
        assert "VS Code" in stats["window_log"]
        assert stats["window_log"]["VS Code"]["seconds"] >= 0

    @patch("tracker._get_active_window_title")
    def test_distraction_time_tracked_separately(self, mock_win, cfg):
        tracker = WindowTracker(cfg)

        mock_win.return_value = "YouTube"
        for _ in range(3):
            tracker.tick()
            time.sleep(0.05)

        mock_win.return_value = "VS Code"
        tracker.tick()

        stats = tracker.get_stats()
        assert stats["distraction_seconds"] > 0
