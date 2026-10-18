"""Persistent bot state (survives crashes and restarts) plus an append-only event log.

state.json     - one record per gotobi day the bot has handled (open / closed / skipped / missed / dryrun), the
                 balance peak, the kill-switch flag and the account the journal belongs to. Written atomically
                 (temp file + rename), so a power cut leaves either the old or the new file.
state.json.bak - a second copy, rewritten after every save, so it holds the latest state too (kill switch
                 included). If state.json cannot be read or has the wrong structure (disk fault, a bad hand edit),
                 the bot starts from the backup. The broker's positions and deal history fill in anything missing
                 (engine._reconcile and _recover_from_history). The unreadable file is kept as
                 state.corrupt-<time>.json. With no usable backup either, it starts empty and the engine halts new
                 trades until `--clear-halt` (nothing is known about the kill switch).
events.jsonl   - every change, timestamped, for auditing (rotated to events.1.jsonl at 20 MB).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("gotobi.journal")
EVENTS_MAX_BYTES = 20_000_000


def _time(value, what: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{what} must be a time")
    datetime.fromisoformat(value)                       # raises ValueError if it is not one


def check_state(data) -> None:
    """Raise ValueError unless `data` has the structure the bot writes and reads (valid JSON can still be the
    wrong shape, and a wrong field would crash the bot later instead of now)."""
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    slots = data.get("slots", {})
    if not isinstance(slots, dict) or not all(isinstance(k, str) and isinstance(v, dict) for k, v in slots.items()):
        raise ValueError("'slots' must map dates to records")
    for key, rec in slots.items():
        if not isinstance(rec.get("status"), str):
            raise ValueError(f"slot {key}: no status")
        if rec["status"] == "open":                     # what the engine reads to manage and close the trade
            if not isinstance(rec.get("ticket"), int) or isinstance(rec.get("ticket"), bool):
                raise ValueError(f"slot {key}: an open trade needs its ticket")
            _time(rec.get("exit_due"), f"slot {key}: exit_due")
        for f in ("r", "pnl", "risk_amount"):
            v = rec.get(f)
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v != v):
                raise ValueError(f"slot {key}: {f} must be a number")
        if rec.get("closed") is not None:
            _time(rec["closed"], f"slot {key}: closed")
    peak = data.get("peak_balance")
    if peak is not None and (not isinstance(peak, (int, float)) or isinstance(peak, bool) or not peak == peak):
        raise ValueError("'peak_balance' must be a number")
    halted = data.get("halted")
    if halted is not None:
        if not isinstance(halted, dict) or not isinstance(halted.get("reason"), str):
            raise ValueError("'halted' must have a reason")
        _time(halted.get("at"), "'halted' at")
    if data.get("reopen_at") is not None:
        _time(data["reopen_at"], "'reopen_at'")
    if data.get("r_reset_at") is not None:
        _time(data["r_reset_at"], "'r_reset_at'")
    account = data.get("account")
    if account is not None and not (isinstance(account, list) and len(account) == 2 and isinstance(account[1], str)):
        raise ValueError("'account' must be [login, server]")


class Journal:
    def __init__(self, state_dir: str | Path, durable: bool = True):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "state.json"
        self.backup = self.dir / "state.json.bak"
        self.events = self.dir / "events.jsonl"
        self.marker = self.dir / "HALTED"      # the kill switch, kept a second way: survives losing state.json
        self.durable = durable          # fsync every write (live); replays switch it off for speed
        self.recovered_from: str | None = None     # "backup" / "nothing" when state.json could not be read
        data = self._load()
        self.slots: dict[str, dict] = data.get("slots", {})
        self.peak_balance: float | None = data.get("peak_balance")
        self.halted: dict | None = data.get("halted")
        self.reopen_at: str | None = data.get("reopen_at")      # when prices last resumed after a market closure
        self.account: list | None = data.get("account")         # [login, server] this journal belongs to
        self.r_reset_at: str | None = data.get("r_reset_at")    # the kill switch's R window starts here
        self._open = {k for k, v in self.slots.items() if v.get("status") == "open"}
        if self.halted is None and self.marker.exists():      # state.json (or its backup) lost the kill switch
            reason = self.marker.read_text(encoding="utf-8", errors="replace").strip() or "kill switch"
            self.halted = {"reason": f"{reason} (restored from the HALTED file)",
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            log.critical("the kill switch was missing from state.json but the HALTED file is there: it stays on")

    def _load(self) -> dict:
        if not self.path.exists():
            if self.backup.exists():                 # a crash between the two renames of an old version
                return self._from_backup("state.json is missing")
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            check_state(data)
        except (ValueError, UnicodeDecodeError) as e:
            bad = self.dir / f"state.corrupt-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
            os.replace(self.path, bad)
            return self._from_backup(f"state.json could not be read ({e}); kept as {bad.name}")
        try:                                         # this one is good: keep a copy for next time
            tmp = self.dir / "state.json.bak.tmp"
            shutil.copyfile(self.path, tmp)
            os.replace(tmp, self.backup)
        except OSError as e:
            log.warning("could not back up state.json: %s", e)
        return data

    def _from_backup(self, why: str) -> dict:
        try:
            data = json.loads(self.backup.read_text(encoding="utf-8"))
            check_state(data)
            self.recovered_from = "backup"
            log.critical("%s: starting from the backup copy; the broker's positions and deal history will fill in "
                         "anything newer", why)
            return data
        except (OSError, ValueError, UnicodeDecodeError):
            pass
        self.recovered_from = "nothing"
        log.critical("%s and there is no usable backup: starting with an empty journal; open positions are "
                     "adopted from the broker and today's trades are checked against its deal history", why)
        return {}

    def save(self) -> None:
        payload = json.dumps({"slots": self.slots, "peak_balance": self.peak_balance, "halted": self.halted,
                              "reopen_at": self.reopen_at, "account": self.account, "r_reset_at": self.r_reset_at},
                             indent=1, sort_keys=True)
        self._write(self.path, payload)
        try:
            self._write(self.backup, payload)          # the backup is never older than the last save
        except OSError as e:
            log.warning("could not update state.json.bak: %s", e)

    def _write(self, path: Path, payload: str) -> None:
        """Atomic: write a temp file, then rename it over the target."""
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix="state.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            if self.durable:
                f.flush()
                os.fsync(f.fileno())
        for attempt in range(6):     # Windows: antivirus or backup software can hold the file for a moment
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 5:
                    os.unlink(tmp)
                    raise
                time.sleep(0.05 * (attempt + 1))

    def event(self, record: dict) -> None:
        rec = {"logged": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        try:
            if self.events.stat().st_size > EVENTS_MAX_BYTES:
                os.replace(self.events, self.dir / "events.1.jsonl")
        except OSError:
            pass
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

    def forget(self, key: str, why: str) -> None:
        """Drop a record (an order the broker definitely did not execute, so the slot may be tried again)."""
        if self.slots.pop(key, None) is not None:
            self._open.discard(key)
            self.save()
            self.event({"slot": key, "forgotten": why})

    def pending(self) -> list[tuple[str, dict]]:
        """Orders sent whose outcome is not known yet."""
        return [(k, v) for k, v in sorted(self.slots.items()) if v.get("status") in ("sending", "unknown")]

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

    # ---- account and kill switch
    def set_account(self, login, server: str) -> None:
        if self.account != [login, server]:
            self.account = [login, server]
            self.save()

    def set_peak(self, balance: float) -> None:
        if self.peak_balance is None or balance > self.peak_balance:
            self.peak_balance = balance
            self.save()

    def halt(self, reason: str, at: datetime) -> None:
        self.halted = {"reason": reason, "at": at.isoformat()}
        self._write(self.marker, reason)        # first: even if state.json is lost later, the halt stays
        self.save()
        self.event({"halted": reason})

    def clear_halt(self) -> None:
        """Resume after a kill switch. Both rules restart from now: the balance peak (drawdown rule) and the
        window of the last 60 longs (R rule), or the old losing run would trip it again at once."""
        self.halted, self.peak_balance = None, None
        self.r_reset_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.save()
        self.marker.unlink(missing_ok=True)
        self.event({"halt_cleared": True})
