"""Append-only JSON logs shared by the review, identity-resolution, correction, snapshot and export features.

Entries are never edited or deleted by the application: a later entry supersedes an earlier one for display,
but the earlier entry stays in the file (audit trail). Every entry carries the dataset fingerprint so logs for
different datasets never mix.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class JsonLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def append(self, entry: dict) -> dict:
        entry = dict(entry)
        entry.setdefault("timestamp_utc", utc_now())
        with _lock:
            log = self.load()
            log.append(entry)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
            tmp.replace(self.path)
        return entry

    def for_dataset(self, dataset_fp: str, **filters) -> list[dict]:
        return [e for e in self.load() if e.get("dataset_fingerprint") == dataset_fp
                and all(e.get(k) == v for k, v in filters.items())]

    def latest_by(self, dataset_fp: str, key: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.for_dataset(dataset_fp):
            out[e.get(key)] = e
        return out
