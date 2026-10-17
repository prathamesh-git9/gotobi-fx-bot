"""Persistent bot state (survives crashes and restarts) plus an append-only event log.

state.json   - one record per gotobi day the bot has handled (open / closed / skipped / missed / dryrun), the
               balance peak and the kill-switch flag. Written atomically (temp file + rename).
events.jsonl - every change, timestamped, for auditing.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class Journal:
    def __init__(self, state_dir: str | Path, durable: bool = True):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "state.json"
        self.events = self.dir / "events.jsonl"
        self.durable = durable          # fsync every write (live); replays switch it off for speed
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.slots: dict[str, dict] = data.get("slots", {})
        self.peak_balance: float | None = data.get("peak_balance")
        self.halted: dict | None = data.get("halted")
        self.reopen_at: str | None = data.get("reopen_at")      # when prices last resumed after a market closure
        self._open = {k for k, v in self.slots.items() if v.get("status") == "open"}

    def save(self) -> None:
        payload = json.dumps({"slots": self.slots, "peak_balance": self.peak_balance, "halted": self.halted,
                              "reopen_at": self.reopen_at}, indent=1, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix="state.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            if self.durable:
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def event(self, record: dict) -> None:
        rec = {"logged": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        with self.events.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    # ---- slots
    def get(self, key: str) -> dict | None:
        return self.slots.get(key)

    def update(self, key: str, **fields) -> dict:
        rec = self.slots.setdefault(key, {})
        rec.update(fields)
        if rec.get("status") == "open":
            self._open.add(key)
        else:
            self._open.discard(key)
        self.save()
        self.event({"slot": key, **fields})
        return rec

    def open_slots(self) -> list[tuple[str, dict]]:
        return [(k, self.slots[k]) for k in sorted(self._open)]

    def slot_of_ticket(self, ticket: int | None) -> tuple[str, dict] | None:
        if ticket is None:
            return None
        for k in self._open:
            if self.slots[k].get("ticket") == ticket:
                return k, self.slots[k]
        return None

    def closed(self) -> list[tuple[str, dict]]:
        return [(k, v) for k, v in sorted(self.slots.items()) if v.get("status") == "closed"]

    # ---- kill switch
    def set_peak(self, balance: float) -> None:
        if self.peak_balance is None or balance > self.peak_balance:
            self.peak_balance = balance
            self.save()

    def halt(self, reason: str, at: datetime) -> None:
        self.halted = {"reason": reason, "at": at.isoformat()}
        self.save()
        self.event({"halted": reason})
