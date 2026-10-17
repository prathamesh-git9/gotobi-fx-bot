"""Thin wrapper around the MetaTrader5 module (or fake_mt5.FakeMT5, which has the same API).

Everything that talks to the terminal is here, so the engine can be tested against the simulator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("gotobi.broker")


class BrokerUnavailable(RuntimeError):
    """The terminal did not answer (not running, not logged in, disconnected)."""


@dataclass
class OrderResult:
    ok: bool
    category: str            # done | transient | market_closed | fatal
    retcode: int | None
    price: float = 0.0
    volume: float = 0.0
    order: int = 0
    deal: int = 0
    message: str = ""


class MT5Broker:
    def __init__(self, mt5):
        self.mt5 = m = mt5
        self.done = {m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_PLACED, m.TRADE_RETCODE_DONE_PARTIAL}
        self.transient = {m.TRADE_RETCODE_REQUOTE, m.TRADE_RETCODE_PRICE_CHANGED, m.TRADE_RETCODE_PRICE_OFF,
                          m.TRADE_RETCODE_TIMEOUT, m.TRADE_RETCODE_CONNECTION, m.TRADE_RETCODE_TOO_MANY_REQUESTS,
                          m.TRADE_RETCODE_LOCKED, m.TRADE_RETCODE_FROZEN,
                          m.TRADE_RETCODE_CLIENT_DISABLES_AT}   # Algo Trading switched off: retry until it is on

    # ---- connection
    def connect(self, terminal_path: str = "", login: str | None = None, password: str | None = None,
                server: str | None = None) -> bool:
        kw = {}
        if login:
            kw = {"login": int(login), "password": password or "", "server": server or ""}
        ok = self.mt5.initialize(terminal_path, **kw) if terminal_path else self.mt5.initialize(**kw)
        if not ok:
            log.error("MetaTrader5.initialize failed: %s", self.mt5.last_error())
        return bool(ok)

    def shutdown(self) -> None:
        self.mt5.shutdown()

    # ---- reads
    def account(self):
        return self.mt5.account_info()

    def terminal(self):
        return self.mt5.terminal_info()

    def resolve_symbol(self, candidates) -> str | None:
        for s in candidates:
            info = self.mt5.symbol_info(s)
            if info is None:
                continue
            if not info.visible and not self.mt5.symbol_select(s, True):
                continue
            return s
        return None

    def symbol(self, s: str):
        info = self.mt5.symbol_info(s)
        if info is None:
            raise BrokerUnavailable(f"symbol_info({s}) failed: {self.mt5.last_error()}")
        return info

    def tick(self, s: str):
        return self.mt5.symbol_info_tick(s)

    def positions(self, s: str, magic: int) -> list:
        ps = self.mt5.positions_get(symbol=s)
        if ps is None:   # an error, NOT "no positions": treating it as empty could open a duplicate trade
            raise BrokerUnavailable(f"positions_get failed: {self.mt5.last_error()}")
        return [p for p in ps if p.magic == magic]

    def deals(self, position_id: int) -> list:
        ds = self.mt5.history_deals_get(position=int(position_id))
        return list(ds) if ds else []

    def deals_between(self, date_from, date_to) -> list:
        ds = self.mt5.history_deals_get(date_from, date_to)
        if ds is None:
            raise BrokerUnavailable(f"history_deals_get failed: {self.mt5.last_error()}")
        return list(ds)

    def loss_per_lot(self, s: str, price: float, sl: float) -> float:
        """Money lost by 1 lot bought at `price` and stopped at `sl`, in the account currency."""
        v = self.mt5.order_calc_profit(self.mt5.ORDER_TYPE_BUY, s, 1.0, price, sl)
        if v is not None and v < 0:
            return -v
        info = self.symbol(s)
        per_tick = info.trade_tick_value_loss or info.trade_tick_value
        return (price - sl) / info.trade_tick_size * per_tick

    def margin_per_lot(self, s: str, price: float) -> float | None:
        v = self.mt5.order_calc_margin(self.mt5.ORDER_TYPE_BUY, s, 1.0, price)
        return v if v and v > 0 else None

    def filling_modes(self, s: str) -> list[int]:
        fm = self.symbol(s).filling_mode          # bit 1 = fill-or-kill allowed, bit 2 = immediate-or-cancel
        modes = []
        if fm & 1:
            modes.append(self.mt5.ORDER_FILLING_FOK)
        if fm & 2:
            modes.append(self.mt5.ORDER_FILLING_IOC)
        modes.append(self.mt5.ORDER_FILLING_RETURN)
        return modes

    # ---- orders
    def market_order(self, s: str, side: int, volume: float, sl: float = 0.0, deviation: int = 30, magic: int = 0,
                     comment: str = "", position: int | None = None, check_only: bool = False) -> OrderResult:
        """Buy (side=+1) or sell (side=-1) at market; with `position` it closes that position."""
        m = self.mt5
        tick = m.symbol_info_tick(s)
        if tick is None:
            return OrderResult(False, "transient", None, message=f"no price: {m.last_error()}")
        req = {"action": m.TRADE_ACTION_DEAL, "symbol": s, "volume": float(volume),
               "type": m.ORDER_TYPE_BUY if side > 0 else m.ORDER_TYPE_SELL,
               "price": tick.ask if side > 0 else tick.bid, "deviation": int(deviation), "magic": int(magic),
               "comment": comment[:31], "type_time": m.ORDER_TIME_GTC}
        if sl:
            req["sl"] = float(sl)
        if position:
            req["position"] = int(position)
        last = None
        for fill in self.filling_modes(s):
            req["type_filling"] = fill
            r = m.order_check(req) if check_only else m.order_send(req)
            if r is None:
                return OrderResult(False, "transient", None, message=f"no answer from terminal: {m.last_error()}")
            rc = r.retcode
            if check_only:
                ok = rc in (0, m.TRADE_RETCODE_DONE)
                return OrderResult(ok, "done" if ok else "fatal", rc, req["price"], req["volume"], message=r.comment)
            if rc in self.done:
                return OrderResult(True, "done", rc, r.price, r.volume, r.order, r.deal, r.comment)
            if rc == m.TRADE_RETCODE_INVALID_FILL:
                last = r
                continue
            if rc in self.transient:
                cat = "transient"
            elif rc == m.TRADE_RETCODE_MARKET_CLOSED:
                cat = "market_closed"
            else:
                cat = "fatal"
            return OrderResult(False, cat, rc, message=r.comment)
        return OrderResult(False, "fatal", last.retcode if last else None, message="no filling mode accepted")
