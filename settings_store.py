"""Alert settings saved to a JSON file so they survive server restarts."""

import json
import threading
from pathlib import Path

DEFAULTS = {
    "notify_no_smoke": False,  # also alert (UI + email) when an image has no smoke
    "confidence": None,  # set in /admin; None = use CONFIDENCE_THRESHOLD from .env
    "email_cooldown_min": 0,  # minutes between alert emails of the same kind; 0 = no limit
}


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._settings = dict(DEFAULTS)
        if path.exists():
            saved = json.loads(path.read_text())
            self._settings.update({k: v for k, v in saved.items() if k in DEFAULTS})

    def get(self) -> dict:
        with self._lock:
            return dict(self._settings)

    def update(self, changes: dict) -> dict:
        with self._lock:
            self._settings.update({k: v for k, v in changes.items() if k in DEFAULTS})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._settings, indent=2))
            return dict(self._settings)
