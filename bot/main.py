"""Run the Gotobi bot against a MetaTrader 5 terminal (Windows, terminal running and logged in).

  python -m bot.main --config bot_config.toml              trade (demo accounts only, unless unlocked)
  python -m bot.main --config bot_config.toml --dry-run    check each order with order_check, send nothing
  python -m bot.main --config bot_config.toml --status     print the next trade and the journal, then exit

Real money needs BOTH allow_live = true in the config and the --allow-live flag.
Login details can come from the environment (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER); otherwise the terminal's
saved login is used.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .broker import BrokerUnavailable, MT5Broker
from .clock import Clock
from .config import ConfigError, load_config
from .engine import Engine, LiveAccountRefused, StartupError
from .journal import Journal

log = logging.getLogger("gotobi")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def setup_logging(state_dir: str) -> None:
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    fmt.converter = time.gmtime   # log times in UTC, like every time in the bot
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(Path(state_dir) / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.handlers[:] = [fh, sh]


class SingleInstance:
    """Holds an OS file lock for the life of the process: a second copy of the bot would trade twice."""

    def __init__(self, path: Path):
        self.f = open(path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit(f"another copy of the bot is already running ({path} is locked)")


def keep_awake() -> None:
    """Stop Windows from sleeping while the bot runs (a sleeping PC misses the 00:54 UTC exit)."""
    if os.name == "nt":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def account_lock_path(login, server) -> Path:
    """One bot per trading account, whatever its config or state folder (two would both trade)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{login}-{server}")
    return Path(tempfile.gettempdir()) / f"gotobi-account-{safe}.lock"


def next_poll(engine, now_fn) -> float:
    """Seconds until the next poll. A failure here must not end the loop: poll again in a second."""
    try:
        return min(60.0, max(0.001, float(engine.poll_interval(now_fn()))))
    except Exception:
        log.exception("could not work out the next poll time; polling again in 1 s")
        return 1.0


def retry_delay(engine, now, failures: int) -> float:
    """Back off after errors (5 s, 10 s, ... up to 60 s), but retry every second when a trade action is due within
    5 minutes: the fix-second sell has a 5-second window."""
    delay = min(60.0, 5.0 * failures)
    try:
        if not engine.quiet(now):
            delay = min(delay, 1.0)
    except Exception:
        delay = min(delay, 1.0)
    return delay


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gotobi USD/JPY bot for MetaTrader 5")
    ap.add_argument("--config", help="TOML settings file (defaults are the backtested rule)")
    ap.add_argument("--dry-run", action="store_true", help="validate orders with order_check, never send them")
    ap.add_argument("--allow-live", action="store_true", help="second key for real-money accounts")
    ap.add_argument("--status", action="store_true", help="print the next trade and journal summary, then exit")
    ap.add_argument("--preflight", action="store_true", help="check terminal, account and a test order (no trade)")
    ap.add_argument("--clear-halt", action="store_true",
                    help="switch the kill switch off (and restart the drawdown peak from today), then exit")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except (ConfigError, OSError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    setup_logging(cfg.state_dir)
    lock = SingleInstance(Path(cfg.state_dir) / "bot.lock")  # noqa: F841 (held until exit)
    if args.clear_halt:
        journal = Journal(cfg.state_dir)
        was = journal.halted
        journal.clear_halt()
        print(f"kill switch cleared (it was: {was['reason'] if was else 'not on'}); the drawdown peak restarts "
              "from the balance at the next start")
        return 0

    clock = Clock(cfg.time_servers) if cfg.clock_sync else None
    if clock is not None:
        clock.refresh()
    now_fn = clock.now if clock is not None else utcnow

    import MetaTrader5 as mt5   # Windows-only package; imported here so the rest is testable anywhere
    broker = MT5Broker(mt5)
    creds = (os.environ.get("MT5_LOGIN"), os.environ.get("MT5_PASSWORD"), os.environ.get("MT5_SERVER"))
    if not broker.connect(cfg.terminal_path, *creds):
        return 3
    acct = broker.account()
    if acct is None:
        log.critical("startup failed: no account information (is MetaTrader 5 logged in?)")
        return 3
    if not (args.preflight or args.status):
        account_lock = SingleInstance(account_lock_path(acct.login, acct.server))  # noqa: F841 (held until exit)
    try:
        journal = Journal(cfg.state_dir)
    except OSError as e:
        log.critical("startup failed: cannot use the state folder %s: %s", cfg.state_dir, e)
        return 3
    engine = Engine(cfg, broker, journal, dry_run=args.dry_run, allow_live_flag=args.allow_live)
    engine.clock_note = clock.describe() if clock is not None else "PC clock used as it is (clock_sync = false)"
    engine.now_fn = now_fn
    if clock is not None:
        engine.clock_ok = clock.verified
    try:
        engine.startup(now_fn(), inspect_only=args.preflight)
        if args.preflight:
            ready, report = engine.preflight(now_fn())
            print("\n".join(report))
            return 0 if ready else 1
    except LiveAccountRefused as e:
        log.critical("%s", e)
        return 2
    except (StartupError, BrokerUnavailable) as e:
        log.critical("startup failed: %s", e)
        return 3
    if args.status:
        print(engine.status(now_fn()))
        return 0

    keep_awake()
    failures = 0
    # Nothing in this loop may end it except Ctrl+C: an open trade must still be closed on time.
    while True:
        try:
            now = now_fn()
            if clock is not None:
                try:
                    if engine.quiet(now):
                        clock.maybe_refresh()     # network call: never right before a trade action
                        now = now_fn()
                except Exception:
                    log.exception("clock check failed; carrying on with the current correction")
            engine.step(now)
            failures = 0
        except BrokerUnavailable as e:
            failures += 1
            log.error("terminal unavailable (%s); reconnecting (attempt %d)", e, failures)
            try:
                broker.shutdown()
                time.sleep(retry_delay(engine, now_fn(), failures))
                if broker.connect(cfg.terminal_path, *creds):
                    log.info("reconnected")
            except KeyboardInterrupt:
                log.info("stopped by user")
                return 0
            except Exception:
                log.exception("reconnect attempt failed")
            continue
        except KeyboardInterrupt:
            log.info("stopped by user")
            return 0
        except Exception:
            failures += 1
            log.exception("unexpected error (attempt %d); continuing", failures)
            try:
                time.sleep(retry_delay(engine, now_fn(), failures))
            except KeyboardInterrupt:
                log.info("stopped by user")
                return 0
            continue
        try:
            time.sleep(next_poll(engine, now_fn))
        except KeyboardInterrupt:
            log.info("stopped by user")
            return 0


if __name__ == "__main__":
    sys.exit(main())
