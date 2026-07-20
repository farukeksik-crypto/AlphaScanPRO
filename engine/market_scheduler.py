from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass
class JobClock:
    last_run: datetime | None = None

    def due(self, now: datetime, interval_minutes: int) -> bool:
        if self.last_run is None:
            return True
        return now >= self.last_run + timedelta(minutes=max(1, interval_minutes))

    def mark(self, now: datetime) -> None:
        self.last_run = now


def zoned_now(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def _parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def bist_market_open(now: datetime, start: str, end: str) -> bool:
    if now.weekday() >= 5:
        return False
    local_time = now.timetz().replace(tzinfo=None)
    return _parse_clock(start) <= local_time <= _parse_clock(end)
