"""SQLite store for readings: the history the diagnosis compares the present with.

One table, one row per reading. Writes are batched (one transaction per sampling round) and rows
older than `keep_days` are removed, so the file stays about the same size, like a ring buffer.
Times are ISO strings without a time zone (local time), which sort in time order.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .readings import Reading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    time TEXT NOT NULL, name TEXT NOT NULL, value REAL, text TEXT, unit TEXT NOT NULL, quality TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_name_time ON readings (name, time);
"""


@dataclass
class Window:
    """Statistics of one reading over a time window; slope is per minute (least squares)."""
    count: int
    mean: float | None
    minimum: float | None
    maximum: float | None
    first: float | None
    last: float | None
    slope_per_minute: float | None


def slope_per_minute(points: list[tuple[str, float]]) -> float | None:
    if len(points) < 2:
        return None
    start = datetime.fromisoformat(points[0][0])
    xs = [(datetime.fromisoformat(t) - start).total_seconds() / 60 for t, _ in points]
    ys = [v for _, v in points]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread


def window_of(points: list[tuple[str, float]]) -> Window:
    values = [v for _, v in points]
    if not values:
        return Window(0, None, None, None, None, None, None)
    return Window(len(values), sum(values) / len(values), min(values), max(values), values[0], values[-1],
                  slope_per_minute(points))


class Store:
    def __init__(self, path: Path | str, keep_days: int = 7) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.keep_days = keep_days
        self.db = sqlite3.connect(str(self.path))
        self.db.executescript(_SCHEMA)

    def write(self, readings: list[Reading]) -> int:
        rows = []
        for r in readings:
            number = float(r.value) if isinstance(r.value, (int, float)) and not isinstance(r.value, bool) else None
            text = r.value if isinstance(r.value, str) else None
            rows.append((r.time, r.name, number, text, r.unit, r.quality))
        with self.db:
            self.db.executemany("INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    def latest(self, name: str) -> Reading | None:
        row = self.db.execute(
            "SELECT time, value, text, unit, quality FROM readings WHERE name = ? ORDER BY time DESC LIMIT 1", (name,)
        ).fetchone()
        if not row:
            return None
        time, value, text, unit, quality = row
        return Reading(name, text if text is not None else value, unit, time, quality)

    def series(self, name: str, minutes: float, until: str | None = None) -> list[tuple[str, float]]:
        end = datetime.fromisoformat(until) if until else datetime.now()
        start = (end - timedelta(minutes=minutes)).isoformat(timespec="seconds")
        rows = self.db.execute(
            "SELECT time, value FROM readings WHERE name = ? AND time >= ? AND time <= ? AND value IS NOT NULL "
            "AND quality != 'missing' ORDER BY time", (name, start, end.isoformat(timespec="seconds"))
        ).fetchall()
        return [(t, v) for t, v in rows]

    def window(self, name: str, minutes: float, until: str | None = None) -> Window:
        return window_of(self.series(name, minutes, until))

    def prune(self, until: str | None = None) -> int:
        end = datetime.fromisoformat(until) if until else datetime.now()
        cutoff = (end - timedelta(days=self.keep_days)).isoformat(timespec="seconds")
        with self.db:
            return self.db.execute("DELETE FROM readings WHERE time < ?", (cutoff,)).rowcount

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def close(self) -> None:
        self.db.close()
