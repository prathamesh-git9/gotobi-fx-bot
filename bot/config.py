"""Bot settings. The defaults are the backtested Gotobi rule; a TOML file can override any of them."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    # account and instrument
    symbols: tuple[str, ...] = ("USDJPYc", "USDJPYm", "USDJPY")   # the first one the terminal offers is traded
    terminal_path: str = ""              # empty: MetaTrader5.initialize() finds the running terminal itself
    allow_live: bool = False             # a real-money account also needs the --allow-live command-line flag

    # the rule, as backtested
    risk_pct: float = 1.0                # % of equity lost if the stop is hit
    stop_pips: float = 55.0
    entry_utc: str = "15:55"             # on the calendar day before the gotobi day
    fix_utc: str = "00:55"               # 09:55 JST, the Tokyo fix
    exit_minutes_before_fix: int = 1     # close at 00:54 UTC: exiting after the fix gives the edge back
    move_off_jp_holidays: bool = True    # no Tokyo fix on Japanese public holidays
    jp_bank_holidays: bool = True        # ... nor on 31 Dec and 2-3 Jan, when Japanese banks are shut
    fx_closed_mmdd: tuple[str, ...] = ("12-25", "01-01")   # FX market shut at the exit time: skip

    # execution safety
    max_entry_delay_min: int = 120       # give up if the entry cannot be made this long after schedule
    reopen_wait_min: int = 15            # after the weekend reopen, let spreads settle first
    min_hold_min: int = 30               # never open with less than this left before the exit
    max_spread_pips: float = 5.0         # wait while the spread is wider than this
    stale_tick_sec: int = 180            # no tick for this long = market shut or price feed down
    deviation_points: int = 30
    max_margin_use: float = 0.90         # size at most to this share of free margin
    below_min_lot: str = "skip"          # "skip" or "min" when the risk is smaller than one minimum lot

    # kill switch (stops new trades; open trades are still closed on time)
    kill_window: int = 60                # trades
    kill_sum_r: float = -6.0             # halt if the last kill_window trades lost more than this many R
    kill_max_drawdown: float = 0.50      # halt if the balance falls this far below its peak

    # plumbing
    magic: int = 950955
    poll_sec: float = 5.0
    state_dir: str = "bot_state"
    server_utc_offset_hours: float = 0.0  # broker server clock minus UTC (Exness: 0); used to judge tick freshness
    auto_server_offset: bool = True       # measure it from live prices (many brokers run UTC+2/+3 and shift with DST)

    def validate(self) -> "Config":
        hhmm = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        checks = [
            (len(self.symbols) > 0, "symbols must not be empty"),
            (0 < self.risk_pct <= 20, "risk_pct must be in (0, 20]"),
            (10 <= self.stop_pips <= 300, "stop_pips must be in [10, 300]"),
            (bool(hhmm.match(self.entry_utc)), "entry_utc must be HH:MM"),
            (bool(hhmm.match(self.fix_utc)), "fix_utc must be HH:MM"),
            (0 <= self.exit_minutes_before_fix <= 60, "exit_minutes_before_fix must be in [0, 60]"),
            (all(re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", x) for x in self.fx_closed_mmdd),
             "fx_closed_mmdd entries must be MM-DD"),
            (0 <= self.max_entry_delay_min <= 600, "max_entry_delay_min must be in [0, 600]"),
            (0 <= self.reopen_wait_min <= 120, "reopen_wait_min must be in [0, 120]"),
            (0 <= self.min_hold_min <= 480, "min_hold_min must be in [0, 480]"),
            (self.max_spread_pips > 0, "max_spread_pips must be > 0"),
            (30 <= self.stale_tick_sec <= 3600, "stale_tick_sec must be in [30, 3600]"),
            (0 <= self.deviation_points <= 1000, "deviation_points must be in [0, 1000]"),
            (0 < self.max_margin_use <= 1, "max_margin_use must be in (0, 1]"),
            (self.below_min_lot in ("skip", "min"), 'below_min_lot must be "skip" or "min"'),
            (self.kill_window >= 10, "kill_window must be >= 10"),
            (0 < self.kill_max_drawdown < 1, "kill_max_drawdown must be in (0, 1)"),
            (self.magic > 0, "magic must be > 0"),
            (0.5 <= self.poll_sec <= 60, "poll_sec must be in [0.5, 60]"),
            (-14 <= self.server_utc_offset_hours <= 14, "server_utc_offset_hours must be in [-14, 14]"),
        ]
        bad = [msg for ok, msg in checks if not ok]
        if bad:
            raise ConfigError("; ".join(bad))
        return self


def load_config(path: str | Path | None) -> Config:
    """Defaults, overridden by the keys in a TOML file. Unknown keys and wrong types are errors."""
    if path is None:
        return Config().validate()
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    known = {f.name: f for f in fields(Config)}
    unknown = sorted(set(raw) - set(known))
    if unknown:
        raise ConfigError(f"unknown settings: {', '.join(unknown)}")
    defaults = Config()
    values = {}
    for key, val in raw.items():
        default = getattr(defaults, key)
        if isinstance(default, tuple):
            if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                raise ConfigError(f"{key} must be a list of strings")
            val = tuple(val)
        elif isinstance(default, bool):
            if not isinstance(val, bool):
                raise ConfigError(f"{key} must be true or false")
        elif isinstance(default, float):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ConfigError(f"{key} must be a number")
            val = float(val)
        elif isinstance(default, int):
            if isinstance(val, bool) or not isinstance(val, int):
                raise ConfigError(f"{key} must be a whole number")
        elif isinstance(default, str) and not isinstance(val, str):
            raise ConfigError(f"{key} must be text")
        values[key] = val
    return Config(**values).validate()
