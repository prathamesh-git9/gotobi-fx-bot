"""Position sizing and settings validation."""
import pytest

from bot.config import Config, ConfigError, load_config
from bot.sizing import round_down, size_position


def test_round_down_handles_float_noise():
    assert round_down(0.07, 0.01) == 0.07
    assert round_down(0.0699999, 0.01) == 0.06
    assert round_down(0.559, 0.01) == 0.55
    assert round_down(1.0, 0.1) == 1.0


def test_risk_based_size():
    s = size_position(100.0, 181.0, 0.01, 200, 0.01, None, 1000)
    assert s.lots == 0.55 and s.risk_at_size <= 100.0 and s.note == "ok"


def test_margin_cap():
    s = size_position(100.0, 181.0, 0.01, 200, 0.01, margin_per_lot=2849.0, free_margin=1000, max_margin_use=0.9)
    assert s.lots == 0.31 and "margin" in s.note


def test_volume_max_cap():
    assert size_position(1e7, 1.0, 0.01, 50, 0.01, None, 1e9).lots == 50


def test_below_minimum_lot():
    s = size_position(1.0, 181.0, 0.01, 200, 0.01, None, 100)
    assert s.lots is None and "minimum lot" in s.note
    s = size_position(1.0, 181.0, 0.01, 200, 0.01, None, 100, below_min="min")
    assert s.lots == 0.01 and "above target" in s.note      # one min lot risks 1.81 <= 2 x target
    s = size_position(1.0, 250.0, 0.01, 200, 0.01, None, 100, below_min="min")
    assert s.lots is None                                    # 2.50 > 2 x target: refuse
    s = size_position(1.0, 150.0, 0.01, 200, 0.01, margin_per_lot=500.0, free_margin=1.0, below_min="min")
    assert s.lots is None and "margin" in s.note


@pytest.mark.parametrize("args", [(0, 1, .01, 1, .01), (1, 0, .01, 1, .01), (1, 1, 0, 1, .01), (1, 1, .01, 1, 0)])
def test_invalid_inputs(args):
    assert size_position(*args, None, 100).lots is None


def test_defaults_are_valid_and_backtested():
    c = Config().validate()
    assert (c.stop_pips, c.entry_utc, c.fix_utc, c.exit_minutes_before_fix) == (55.0, "15:55", "00:55", 1)
    assert c.allow_live is False


def test_toml_overrides(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('risk_pct = 10\nsymbols = ["USDJPYc"]\nallow_live = false\n', encoding="utf-8")
    c = load_config(p)
    assert c.risk_pct == 10.0 and c.symbols == ("USDJPYc",)


@pytest.mark.parametrize("text, msg", [
    ("risk_pc = 1", "unknown settings"),
    ("risk_pct = 50", "risk_pct"),
    ('risk_pct = "10"', "number"),
    ("allow_live = 1", "true or false"),
    ('entry_utc = "25:00"', "entry_utc"),
    ('below_min_lot = "maybe"', "below_min_lot"),
    ('symbols = "USDJPY"', "list of strings"),
])
def test_bad_settings(tmp_path, text, msg):
    p = tmp_path / "c.toml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=msg):
        load_config(p)
