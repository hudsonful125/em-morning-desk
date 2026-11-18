"""
data/commodities.py: today's moves in oil, copper and soybeans (see config.COMMODITIES).

Uses the same Twelve Data /quote call as data/fx.py (1 credit per symbol) and saves the
results in the same fx_rates table, so asking twice in one day costs nothing.
"""

import config
import db
from data import fx


def symbols():
    return [c["symbol"] for c in config.COMMODITIES]


def get_commodity_moves(conn, date, api_key, refresh=False):
    """
    Today's rows for each commodity fund: {symbol, name, fund, linked, rate, prev_close, pct_change}.
    Returns (rows in config order, warnings). No key = no rows and no extra warning
    (the FX step already warns about a missing key).
    """
    wanted = symbols()
    cached = [] if refresh else [r for r in db.load_fx_rates(conn, date) if r["pair"] in wanted]
    missing = [s for s in wanted if s not in {r["pair"] for r in cached}]
    warnings = []
    if missing and api_key:
        rows, errors = fx.fetch_quotes(missing, api_key)
        warnings += [f"Commodities: {e}" for e in errors]
        if rows:
            db.save_fx_rates(conn, date, rows)
    saved = {r["pair"]: r for r in db.load_fx_rates(conn, date)}
    out = []
    for c in config.COMMODITIES:
        if c["symbol"] in saved:
            row = saved[c["symbol"]]
            out.append(dict(c, rate=row["rate"], prev_close=row["prev_close"], pct_change=row["pct_change"]))
    return out, warnings
