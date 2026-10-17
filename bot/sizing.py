"""Position size: the lots at which hitting the stop loses the chosen risk, within broker and margin limits."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Size:
    lots: float | None      # None = do not trade
    risk_at_size: float     # money lost at the stop with this size
    note: str


def round_down(x: float, step: float) -> float:
    """Largest multiple of step that is <= x (tolerant of float noise such as 0.07/0.01 = 6.999...)."""
    return round(math.floor(x / step + 1e-9) * step, 8)


def size_position(risk_amount: float, loss_per_lot: float, vmin: float, vmax: float, step: float,
                  margin_per_lot: float | None, free_margin: float, max_margin_use: float = 0.9,
                  below_min: str = "skip") -> Size:
    if not (risk_amount > 0 and loss_per_lot > 0 and step > 0 and vmin > 0 and vmax >= vmin):
        return Size(None, 0.0, "invalid sizing inputs")
    lots = round_down(risk_amount / loss_per_lot, step)
    note = "ok"
    if margin_per_lot:
        cap = round_down(max(free_margin, 0.0) * max_margin_use / margin_per_lot, step)
        if lots > cap:
            lots, note = cap, "reduced to fit the margin limit"
    if lots > vmax:
        lots, note = round_down(vmax, step), "capped at the broker's maximum volume"
    if lots < vmin - 1e-12:
        min_fits_margin = not margin_per_lot or vmin * margin_per_lot <= max(free_margin, 0.0) * max_margin_use
        if below_min == "min" and vmin * loss_per_lot <= 2 * risk_amount and min_fits_margin:
            return Size(vmin, vmin * loss_per_lot, "minimum lot (risk above target)")
        if not min_fits_margin:
            return Size(None, vmin * loss_per_lot, "not enough free margin for one minimum lot")
        return Size(None, vmin * loss_per_lot,
                    f"one minimum lot ({vmin}) would risk {vmin * loss_per_lot:.2f}, more than {risk_amount:.2f}")
    return Size(lots, lots * loss_per_lot, note)
