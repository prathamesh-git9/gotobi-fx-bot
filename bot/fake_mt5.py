"""A MetaTrader5-compatible simulator for tests and historical replays, driven by minute bid/ask bars.

It has the real package's function names, constants and result fields (generated into _mt5_api.py and checked by
tests/test_api_surface.py), so the bot runs on it unchanged.
  prices  at time `now` the tick is the opening price of that minute's bar; in a gap (market shut) it is the last
          bar's close stamped with that bar's time, so prices go stale exactly as they do in the terminal
  stops   triggered on bar lows (buys) / highs (sells) between successive set_time() calls, from the bar the
          position was opened in; a stop gapped through fills at the bar's open. Take-profits likewise on bar
          highs (buys) / lows (sells); if stop and target are both touched in one minute, the stop wins
  fills   market orders fill at the current ask / bid, `slip_bp` basis points worse
  money   EUR account: JPY profit -> USD at the closing price -> EUR at the EUR/USD rate of that moment
Fault injection: fail_next(), positions_fail, connected, trade_mode, filling_mode.
"""
from __future__ import annotations

from datetime import timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ._mt5_api import CONSTANTS, FIELDS

REQUEST_KEYS = {"action", "magic", "order", "symbol", "volume", "price", "stoplimit", "sl", "tp", "deviation", "type",
                "type_filling", "type_time", "expiration", "comment", "position", "position_by"}
TEXT_FIELDS = {"symbol", "comment", "external_id", "name", "server", "currency", "company", "path", "data_path",
               "commondata_path", "language", "basis", "category", "currency_base", "currency_profit",
               "currency_margin", "bank", "description", "exchange", "formula", "isin", "page"}


def make(kind: str, **values) -> SimpleNamespace:
    """A result object with exactly the real type's fields (unknown names are an error)."""
    unknown = set(values) - set(FIELDS[kind])
    if unknown:
        raise AttributeError(f"{kind} has no field(s) {sorted(unknown)}")
    rec = {f: ("" if f in TEXT_FIELDS else 0) for f in FIELDS[kind]}
    rec.update(values)
    return SimpleNamespace(**rec)


class FakeMT5:
    def __init__(self, bars: pd.DataFrame, eurusd: pd.Series | float = 1.17, symbol: str = "USDJPYm",
                 balance: float = 1000.0, currency: str = "EUR", leverage: int = 30, trade_mode: int = 0,
                 slip_bp: float = 0.2, filling_mode: int = 2, digits: int = 3, contract: float = 100_000.0,
                 vmin: float = 0.01, vmax: float = 200.0, vstep: float = 0.01, server_offset_h: float = 0.0,
                 stops_level: int = 0):
        for k, v in CONSTANTS.items():
            setattr(self, k, v)
        self.name = symbol
        idx = pd.DatetimeIndex(bars.index)
        self.t = idx.values.astype("datetime64[m]").astype(np.int64)
        self.bo, self.bh, self.bl, self.bc = (bars[c].to_numpy(float) for c in ("bopen", "bhigh", "blow", "bclose"))
        self.ao, self.ah, self.al, self.ac = (bars[c].to_numpy(float) for c in ("aopen", "ahigh", "alow", "aclose"))
        if isinstance(eurusd, (int, float)):
            self._eu_t, self._eu_v = None, float(eurusd)
        else:
            self._eu_t = pd.DatetimeIndex(eurusd.index).values.astype("datetime64[m]").astype(np.int64)
            self._eu_v = eurusd.to_numpy(float)
        self.balance, self.currency, self.leverage, self.trade_mode = float(balance), currency, leverage, trade_mode
        self.slip = slip_bp * 1e-4
        self.filling_mode, self.digits, self.point = filling_mode, digits, 10.0 ** -digits
        self.contract, self.vmin, self.vmax, self.vstep = contract, vmin, vmax, vstep
        self.offset_s = server_offset_h * 3600
        self.stops_level = stops_level
        self.positions: dict[int, SimpleNamespace] = {}
        self.orders: dict[int, SimpleNamespace] = {}      # live (queued) orders: only via queue_order()
        self._queued: dict[int, dict] = {}
        self._open_minute: dict[int, int] = {}
        self.deal_log: list[SimpleNamespace] = []
        self.requests: list[dict] = []
        self._faults: list[dict] = []
        self.positions_fail = 0
        self.connected = True
        self.algo_trading = True          # the terminal's Algo Trading button
        self.tradeapi_disabled = False    # Tools > Options > Expert Advisors > "Disable ... via external Python API"
        self.initialized_with = None
        self.error = (1, "Success")
        self._next = 1_000_000
        self.now = None
        self.minute = None
        self.processed = None

    # ------------------------------------------------------------------ simulation control
    def set_time(self, now) -> None:
        """Move the clock forward (aware UTC datetime), triggering any stops in the bars passed."""
        m = int(now.timestamp() // 60)
        if self.processed is not None and m > self.processed:
            self._run_stops(self.processed, m)
        self.processed = m if self.processed is None else max(self.processed, m)
        self.now, self.minute = now, m

    def queue_order(self, request: dict) -> int:
        """Test hook: the broker queues this market request as a live order (what a TRADE_RETCODE_PLACED reply
        means) instead of filling it. fill_order() fills it later; a TRADE_ACTION_REMOVE request cancels it."""
        ticket = self._id()
        stamp = (self.now.timestamp() if self.now else 0) + self.offset_s
        self.orders[ticket] = make("TradeOrder", ticket=ticket, time_setup=int(stamp), time_setup_msc=int(stamp * 1000),
                                   type=request["type"], state=self.ORDER_STATE_PLACED,
                                   magic=int(request.get("magic", 0)), volume_initial=request["volume"],
                                   volume_current=request["volume"], price_open=request.get("price", 0.0),
                                   sl=float(request.get("sl", 0.0) or 0.0), tp=float(request.get("tp", 0.0) or 0.0),
                                   symbol=self.name, comment=request.get("comment", ""))
        self._queued[ticket] = dict(request)
        return ticket

    def fill_order(self, ticket: int):
        """Test hook: the queued order fills now (at the current price)."""
        self.orders.pop(ticket)
        return self.order_send(self._queued.pop(ticket))

    def fail_next(self, kind: str, retcode: int | None, times: int = 1) -> None:
        """Make the next `times` order_send calls of kind 'open', 'close' or 'any' return `retcode` (None = no answer)."""
        self._faults.append({"kind": kind, "retcode": retcode, "times": times})

    # ------------------------------------------------------------------ internals
    def _id(self) -> int:
        self._next += 1
        return self._next

    def _eur(self) -> float:
        if self._eu_t is None:
            return self._eu_v
        i = max(int(np.searchsorted(self._eu_t, self.minute, side="right")) - 1, 0)
        return float(self._eu_v[i])

    def _tick(self):
        if self.minute is None:
            return None
        i = int(np.searchsorted(self.t, self.minute, side="right")) - 1
        if i < 0:
            return None
        if self.t[i] == self.minute:
            return self.bo[i], self.ao[i], self.now.timestamp()
        return self.bc[i], self.ac[i], float(self.t[i] * 60 + 59)

    def _market_open(self) -> bool:
        i = int(np.searchsorted(self.t, self.minute, side="left"))
        return i < len(self.t) and self.t[i] == self.minute

    def _profit(self, typ: int, volume: float, open_px: float, close_px: float) -> float:
        diff = (close_px - open_px) if typ == self.ORDER_TYPE_BUY else (open_px - close_px)
        return volume * self.contract * diff / close_px / self._eur()

    def _margin(self, volume: float) -> float:
        return volume * self.contract / self.leverage / self._eur()

    def _floating(self) -> float:
        tk = self._tick()
        if tk is None:
            return 0.0
        bid, ask, _ = tk
        return sum(self._profit(p.type, p.volume, p.price_open, bid if p.type == 0 else ask)
                   for p in self.positions.values())

    def _close(self, p, price: float, ts: float, reason: int, volume: float | None = None) -> SimpleNamespace:
        vol = p.volume if volume is None else volume
        profit = self._profit(p.type, vol, p.price_open, price)
        self.balance += profit
        deal = make("TradeDeal", ticket=self._id(), order=self._id(), time=int(ts + self.offset_s),
                    time_msc=int((ts + self.offset_s) * 1000), type=1 - p.type, entry=self.DEAL_ENTRY_OUT,
                    magic=p.magic, position_id=p.identifier, reason=reason, volume=vol, price=price,
                    profit=round(profit, 2), symbol=p.symbol, comment=p.comment)
        self.deal_log.append(deal)
        if vol >= p.volume - 1e-9:
            del self.positions[p.ticket]
            self._open_minute.pop(p.ticket, None)
        else:
            p.volume = round(p.volume - vol, 8)
        return deal

    def _run_stops(self, a: int, b: int) -> None:
        if not self.positions:
            return
        i1 = int(np.searchsorted(self.t, b, side="left"))
        for p in list(self.positions.values()):
            if not p.sl and not p.tp:
                continue
            j0 = int(np.searchsorted(self.t, max(a, self._open_minute[p.ticket]), side="left"))
            if j0 >= i1:
                continue
            buy = p.type == self.POSITION_TYPE_BUY
            ks = kt = None
            if p.sl:
                hit = np.flatnonzero(self.bl[j0:i1] <= p.sl) if buy else np.flatnonzero(self.ah[j0:i1] >= p.sl)
                ks = j0 + int(hit[0]) if len(hit) else None
            if p.tp:
                hit = np.flatnonzero(self.bh[j0:i1] >= p.tp) if buy else np.flatnonzero(self.al[j0:i1] <= p.tp)
                kt = j0 + int(hit[0]) if len(hit) else None
            if ks is not None and (kt is None or ks <= kt):
                k, reason = ks, self.DEAL_REASON_SL
                px = min(p.sl, self.bo[k]) if buy else max(p.sl, self.ao[k])
            elif kt is not None:
                k, reason = kt, self.DEAL_REASON_TP
                px = max(p.tp, self.bo[k]) if buy else min(p.tp, self.ao[k])
            else:
                continue
            self._close(p, px - self.slip * px if buy else px + self.slip * px, float(self.t[k] * 60), reason)

    def _take_fault(self, kind: str):
        for f in self._faults:
            if f["times"] > 0 and f["kind"] in (kind, "any"):
                f["times"] -= 1
                return f
        return None

    def _validate(self, request: dict):
        """Return (retcode, message, context) for a request; retcode 0 means it would execute."""
        bad = set(request) - REQUEST_KEYS
        if bad:
            raise TypeError(f"invalid request keys {sorted(bad)}")
        if request.get("action") != self.TRADE_ACTION_DEAL or request.get("symbol") != self.name:
            return self.TRADE_RETCODE_INVALID, "Invalid request", None
        fill = request.get("type_filling")
        allowed = ({self.ORDER_FILLING_FOK} if self.filling_mode & 1 else set()) | \
                  ({self.ORDER_FILLING_IOC} if self.filling_mode & 2 else set())
        if fill not in allowed:
            return self.TRADE_RETCODE_INVALID_FILL, "Unsupported filling mode", None
        if not self._market_open():
            return self.TRADE_RETCODE_MARKET_CLOSED, "Market closed", None
        vol = float(request.get("volume", 0))
        steps = vol / self.vstep
        if vol < self.vmin - 1e-9 or vol > self.vmax + 1e-9 or abs(steps - round(steps)) > 1e-6:
            return self.TRADE_RETCODE_INVALID_VOLUME, "Invalid volume", None
        bid, ask, ts = self._tick()
        typ = request.get("type")
        if request.get("position"):
            p = self.positions.get(int(request["position"]))
            if p is None:
                return self.TRADE_RETCODE_POSITION_CLOSED, "Position doesn't exist", None
            if typ == p.type or vol > p.volume + 1e-9:
                return self.TRADE_RETCODE_INVALID, "Invalid close request", None
            price = bid - self.slip * bid if p.type == self.POSITION_TYPE_BUY else ask + self.slip * ask
            return 0, "Done", (p, price, ts, vol, bid, ask)
        price = ask + self.slip * ask if typ == self.ORDER_TYPE_BUY else bid - self.slip * bid
        sl = float(request.get("sl", 0.0) or 0.0)
        tp = float(request.get("tp", 0.0) or 0.0)
        gap = self.stops_level * self.point
        if sl and ((typ == self.ORDER_TYPE_BUY and sl >= bid - gap) or (typ == self.ORDER_TYPE_SELL and sl <= ask + gap)):
            return self.TRADE_RETCODE_INVALID_STOPS, "Invalid stops", None
        if tp and ((typ == self.ORDER_TYPE_BUY and tp <= ask + gap) or (typ == self.ORDER_TYPE_SELL and tp >= bid - gap)):
            return self.TRADE_RETCODE_INVALID_STOPS, "Invalid stops", None
        if self._margin(vol) > self.balance + self._floating() - sum(self._margin(q.volume) for q in self.positions.values()):
            return self.TRADE_RETCODE_NO_MONEY, "No money", None
        return 0, "Done", (None, price, ts, vol, bid, ask)

    def _result(self, retcode: int, request: dict, **kw) -> SimpleNamespace:
        return make("OrderSendResult", retcode=retcode, request_id=len(self.requests),
                    request=SimpleNamespace(**request), **kw)

    # ------------------------------------------------------------------ MetaTrader5 API
    def initialize(self, path=None, **kw) -> bool:
        self.initialized_with = (path, kw)
        return self.connected

    def shutdown(self) -> None:
        pass

    def last_error(self):
        return self.error

    def version(self):
        return (500, 5000, "simulator")

    def terminal_info(self):
        if not self.connected:
            return None
        return make("TerminalInfo", connected=True, trade_allowed=self.algo_trading,
                    tradeapi_disabled=self.tradeapi_disabled, build=5000, name="FakeMT5", company="simulator",
                    language="English")

    def account_info(self):
        if not self.connected:
            return None
        floating = self._floating()
        margin = sum(self._margin(p.volume) for p in self.positions.values())
        equity = self.balance + floating
        return make("AccountInfo", login=12345678, trade_mode=self.trade_mode, leverage=self.leverage,
                    limit_orders=1024, trade_allowed=True, trade_expert=True, margin_mode=2, currency_digits=2,
                    balance=round(self.balance, 2), profit=round(floating, 2), equity=round(equity, 2),
                    margin=round(margin, 2), margin_free=round(equity - margin, 2),
                    margin_level=round(equity / margin * 100, 2) if margin else 0.0, margin_so_call=100.0,
                    margin_so_so=50.0, name="Simulator", server="Fake-Server", currency=self.currency,
                    company="simulator")

    def symbol_info(self, symbol: str):
        if symbol != self.name or not self.connected:
            return None
        tk = self._tick()
        bid, ask = (tk[0], tk[1]) if tk else (0.0, 0.0)
        tick_value = self.contract * self.point / (bid or 1.0) / self._eur()
        return make("SymbolInfo", select=True, visible=True, digits=self.digits,
                    spread=int(round((ask - bid) / self.point)), spread_float=True, trade_calc_mode=0,
                    trade_mode=self.SYMBOL_TRADE_MODE_FULL, trade_stops_level=self.stops_level,
                    trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET, swap_rollover3days=3,
                    filling_mode=self.filling_mode, order_mode=127, bid=bid, ask=ask, point=self.point,
                    trade_tick_value=tick_value, trade_tick_value_profit=tick_value, trade_tick_value_loss=tick_value,
                    trade_tick_size=self.point, trade_contract_size=self.contract, volume_min=self.vmin,
                    volume_max=self.vmax, volume_step=self.vstep, currency_base="USD", currency_profit="JPY",
                    currency_margin="USD", description="US Dollar vs Japanese Yen", name=self.name,
                    path=f"Forex\\{self.name}")

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return symbol == self.name

    def symbol_info_tick(self, symbol: str):
        if symbol != self.name or not self.connected:
            return None
        tk = self._tick()
        if tk is None:
            return None
        bid, ask, ts = tk
        ts += self.offset_s
        return make("Tick", time=int(ts), bid=bid, ask=ask, time_msc=int(ts * 1000), flags=6)

    def positions_get(self, symbol: str | None = None, ticket: int | None = None, group: str | None = None):
        if self.positions_fail > 0:
            self.positions_fail -= 1
            self.error = (-10004, "No IPC connection")
            return None
        if not self.connected:
            self.error = (-10004, "No IPC connection")
            return None
        tk = self._tick()
        out = []
        for p in self.positions.values():
            if (symbol is None or p.symbol == symbol) and (ticket is None or p.ticket == ticket):
                cur = (tk[0] if p.type == 0 else tk[1]) if tk else p.price_open
                out.append(make("TradePosition", **{**vars(p), "price_current": cur,
                                                    "profit": round(self._profit(p.type, p.volume, p.price_open, cur), 2)}))
        return tuple(out)

    def orders_get(self, symbol: str | None = None, ticket: int | None = None, group: str | None = None):
        if not self.connected:
            self.error = (-10004, "No IPC connection")
            return None
        return tuple(o for o in self.orders.values()
                     if (symbol is None or o.symbol == symbol) and (ticket is None or o.ticket == ticket))

    def history_deals_get(self, date_from=None, date_to=None, group=None, position=None, ticket=None):
        if not self.connected:
            self.error = (-10004, "No IPC connection")
            return None
        self.error = (1, "Success")

        def secs(x):
            if x is None or isinstance(x, (int, float)):
                return x
            return x.timestamp() if x.tzinfo else x.replace(tzinfo=timezone.utc).timestamp()

        lo, hi = secs(date_from), secs(date_to)
        out = [d for d in self.deal_log
               if (position is None or d.position_id == position) and (ticket is None or d.ticket == ticket)
               and (lo is None or d.time >= lo) and (hi is None or d.time <= hi)]
        return tuple(out)

    def order_calc_profit(self, action: int, symbol: str, volume: float, price_open: float, price_close: float):
        if symbol != self.name:
            return None
        return round(self._profit(action, volume, price_open, price_close), 2)

    def order_calc_margin(self, action: int, symbol: str, volume: float, price: float):
        if symbol != self.name:
            return None
        return round(self._margin(volume), 2)

    def order_check(self, request: dict):
        rc, msg, _ = self._validate(request)
        acct = self.account_info()
        return make("OrderCheckResult", retcode=rc, balance=acct.balance, equity=acct.equity, profit=acct.profit,
                    margin=acct.margin, margin_free=acct.margin_free, margin_level=acct.margin_level, comment=msg,
                    request=SimpleNamespace(**request))

    def order_send(self, request: dict):
        self.requests.append(dict(request))
        f = self._take_fault("close" if request.get("position") else "open")
        if f is not None:
            if f["retcode"] is None:
                self.error = (-10004, "No IPC connection")
                return None
            return self._result(f["retcode"], request, comment="injected fault")
        if not self.connected:
            self.error = (-10004, "No IPC connection")
            return None
        if not self.algo_trading or self.tradeapi_disabled:
            return self._result(self.TRADE_RETCODE_CLIENT_DISABLES_AT, request, comment="AutoTrading disabled by client")
        if request.get("action") == self.TRADE_ACTION_REMOVE:          # cancel a live order
            if self.orders.pop(int(request.get("order", 0)), None) is None:
                return self._result(self.TRADE_RETCODE_INVALID, request, comment="Order not found")
            self._queued.pop(int(request["order"]), None)
            return self._result(self.TRADE_RETCODE_DONE, request, order=int(request["order"]), comment="Request executed")
        rc, msg, ctx = self._validate(request)
        if rc:
            return self._result(rc, request, comment=msg)
        p, price, ts, vol, bid, ask = ctx
        if p is not None:   # close (or reduce) an existing position
            deal = self._close(p, price, ts, self.DEAL_REASON_EXPERT, vol)
            return self._result(self.TRADE_RETCODE_DONE, request, deal=deal.ticket, order=deal.order, volume=vol,
                                price=price, bid=bid, ask=ask, comment="Request executed")
        ticket = self._id()
        typ = request["type"]
        stamp = ts + self.offset_s
        pos = make("TradePosition", ticket=ticket, time=int(stamp), time_msc=int(stamp * 1000), time_update=int(stamp),
                   time_update_msc=int(stamp * 1000), type=typ, magic=int(request.get("magic", 0)), identifier=ticket,
                   reason=3, volume=vol, price_open=price, sl=float(request.get("sl", 0.0) or 0.0),
                   tp=float(request.get("tp", 0.0) or 0.0),
                   price_current=price, symbol=self.name, comment=request.get("comment", ""))
        self.positions[ticket] = pos
        self._open_minute[ticket] = self.minute
        deal = make("TradeDeal", ticket=self._id(), order=ticket, time=int(stamp), time_msc=int(stamp * 1000),
                    type=typ, entry=self.DEAL_ENTRY_IN, magic=pos.magic, position_id=ticket,
                    reason=self.DEAL_REASON_EXPERT, volume=vol, price=price, symbol=self.name, comment=pos.comment)
        self.deal_log.append(deal)
        return self._result(self.TRADE_RETCODE_DONE, request, deal=deal.ticket, order=ticket, volume=vol, price=price,
                            bid=bid, ask=ask, comment="Request executed")
