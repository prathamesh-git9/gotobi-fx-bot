"""The bot and the simulator use only names that exist in the real MetaTrader5 package, with the real values and
fields. If MetaQuotes renames something, these fail before a live order does."""
import ast
from datetime import timezone

import pytest

from bot._mt5_api import CONSTANTS, FIELDS
from bot.fake_mt5 import FakeMT5
from conftest import ROOT, make_bars, utc

mt5 = pytest.importorskip("MetaTrader5")


def real_fields(kind: str) -> list[str]:
    return [n for n, v in vars(getattr(mt5, kind)).items() if type(v).__name__ == "member_descriptor"]


@pytest.mark.parametrize("kind", sorted(FIELDS))
def test_result_fields_match_installed_package(kind):
    assert real_fields(kind) == FIELDS[kind]


def test_constants_match_installed_package():
    wrong = {k: (v, getattr(mt5, k, None)) for k, v in CONSTANTS.items() if getattr(mt5, k, None) != v}
    assert not wrong


def mt5_names_used_by_bot() -> set[str]:
    names = set()
    for f in ("broker.py", "engine.py", "main.py"):
        for node in ast.walk(ast.parse((ROOT / "bot" / f).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                v = node.value
                if (isinstance(v, ast.Name) and v.id in ("m", "mt5")) or (isinstance(v, ast.Attribute) and v.attr == "mt5"):
                    names.add(node.attr)
    return names


def test_bot_calls_only_real_functions_and_constants():
    used = mt5_names_used_by_bot()
    assert {"order_send", "positions_get", "history_deals_get", "ORDER_TYPE_BUY", "TRADE_RETCODE_DONE"} <= used
    assert sorted(n for n in used if not hasattr(mt5, n)) == []


def test_simulator_returns_objects_with_exactly_the_real_fields():
    fake = FakeMT5(make_bars("2026-10-14 15:00", "2026-10-14 17:00"), 1.17)
    fake.set_time(utc("2026-10-14 15:55"))
    r = fake.order_send({"action": 1, "symbol": "USDJPYm", "volume": 0.1, "type": 0, "price": 150.01, "sl": 149.4,
                         "deviation": 30, "magic": 1, "comment": "t", "type_time": 0, "type_filling": 1})
    objects = {"AccountInfo": fake.account_info(), "SymbolInfo": fake.symbol_info("USDJPYm"),
               "Tick": fake.symbol_info_tick("USDJPYm"), "TradePosition": fake.positions_get(symbol="USDJPYm")[0],
               "OrderSendResult": r, "OrderCheckResult": fake.order_check(dict(r.request.__dict__)),
               "TradeDeal": fake.history_deals_get(position=r.order)[0], "TerminalInfo": fake.terminal_info()}
    for kind, obj in objects.items():
        assert set(vars(obj)) == set(real_fields(kind)), kind


def test_simulator_exposes_every_function_the_bot_calls():
    fake = FakeMT5(make_bars("2026-10-14 15:00", "2026-10-14 16:00"), 1.17)
    for name in mt5_names_used_by_bot():
        assert hasattr(fake, name), name
