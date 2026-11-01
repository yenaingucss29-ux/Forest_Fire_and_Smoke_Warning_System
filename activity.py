"""What happened recently: the last 10 checked photos, today's counts and email cooldowns.

Kept in memory only, never on disk, so a server restart clears all of it.
"""

import itertools
import threading
import time
from collections import deque
from datetime import date, datetime, timezone

from detector import DetectionResult
from notifier import EmailStatus

RECENT_LIMIT = 10


class Activity:
    def __init__(self):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._recent = deque(maxlen=RECENT_LIMIT)  # oldest dropped first
        self._last_email = {}  # alert kind ("smoke" / "clear") -> time.monotonic() of its last sent email
        self._day = date.today()
        self._counts = dict.fromkeys(("checks", "smoke", "clear", "emails_sent"), 0)

    def record_check(self, filename: str, result: DetectionResult, image_jpeg: bytes, email: EmailStatus | None):
        with self._lock:
            self._roll_day()
            self._counts["checks"] += 1
            self._counts["smoke" if result.smoke_detected else "clear"] += 1
            self._recent.append({
                "id": next(self._ids),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "filename": filename,
                "smoke_detected": result.smoke_detected,
                "max_smoke_confidence": result.max_smoke_confidence,
                "regions": len(result.smoke),
                "email": email.__dict__ if email else None,
                "image_jpeg": image_jpeg,
            })

    def cooldown_left(self, kind: str, cooldown_min: int) -> float:
        """Seconds until another email of this kind may go out (0 = it can go now)."""
        with self._lock:
            last = self._last_email.get(kind)
        if not cooldown_min or last is None:
            return 0
        return max(0.0, last + cooldown_min * 60 - time.monotonic())

    def email_sent(self, kind: str | None, status: EmailStatus):
        """Count a sent email; for an alert kind, also start that kind's cooldown."""
        if not status.sent:
            return
        with self._lock:
            self._roll_day()
            self._counts["emails_sent"] += 1
            if kind:
                self._last_email[kind] = time.monotonic()

    def snapshot(self) -> tuple[dict, list[dict]]:
        """Today's counts, and the recent checks newest first (without the image bytes)."""
        with self._lock:
            self._roll_day()
            stats = {"date": self._day.isoformat(), **self._counts}
            recent = [{k: v for k, v in p.items() if k != "image_jpeg"} for p in reversed(self._recent)]
        return stats, recent

    def photo(self, photo_id: int) -> bytes | None:
        with self._lock:
            return next((p["image_jpeg"] for p in self._recent if p["id"] == photo_id), None)

    def _roll_day(self):
        if date.today() != self._day:
            self._day = date.today()
            self._counts = dict.fromkeys(self._counts, 0)
