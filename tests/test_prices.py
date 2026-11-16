"""Tests for data/bigmac.py and modules/prices.py. Uses a small saved sample of The Economist's CSV."""

from pathlib import Path

import pytest

from data import bigmac
from modules import prices

FIXTURE = Path(__file__).parent / "fixtures" / "big_mac_sample.csv"


# --- formulas ---------------------------------------------------------------

def test_usd_price():
    assert prices.usd_price(23.9, 5.00) == pytest.approx(4.78)


def test_valuation_pct():
    assert prices.valuation_pct(4.78, 6.22) == pytest.approx(-23.15, abs=0.01)
    assert prices.valuation_pct(7.00, 6.22) > 0


def test_implied_ppp():
    # 23.9 BRL / $6.22 -> USD/BRL would need to be ~3.84 for prices to match
    assert prices.implied_ppp(23.9, 6.22) == pytest.approx(3.8424, abs=1e-4)


def test_usd_price_change_from_fx_move():
    # USD/BRL 5.00 -> 5.10: the same local price buys ~1.96% fewer dollars
    assert prices.usd_price_change_pct(5.00, 5.10) == pytest.approx(-1.9608, abs=1e-4)


# --- reading the CSV ----------------------------------------------------------

def test_reads_latest_price_per_currency():
    local, date = bigmac.read_price_csv(FIXTURE)
    assert date == "2026-07-01"
    assert local["TRY"] == 325       # July 2026, not the January price (255)
    assert local["USD"] == 6.22
    assert set(local) == {"BRL", "TRY", "USD", "INR"}


def test_skips_blank_and_zero_prices():
    rows = [
        {"currency_code": "BRL", "local_price": "0", "date": "2026-07-01"},
        {"currency_code": "MXN", "local_price": "", "date": "2026-07-01"},
        {"currency_code": "USD", "local_price": "6.22", "date": "2026-07-01"},
    ]
    local, _ = bigmac.latest_prices(rows)
    assert local == {"USD": 6.22}


def test_missing_custom_file_warns():
    local, date, warnings = bigmac.get_item_prices({"name": "iPhone", "source": "items/nope.csv"})
    assert local == {} and "not found" in warnings[0]


# --- the table ----------------------------------------------------------------

FX_ROWS = [
    {"pair": "USD/BRL", "rate": 5.7368, "prev_close": 5.6619, "pct_change": 1.3229},
    {"pair": "USD/TRY", "rate": 50.3943, "prev_close": 50.3980, "pct_change": -0.0073},
    {"pair": "USD/MXN", "rate": 18.6319, "prev_close": 18.5431, "pct_change": 0.4789},  # no price in sample
]


def test_table_sorted_and_skips_missing():
    local, _ = bigmac.read_price_csv(FIXTURE)
    table = prices.build_price_table(FX_ROWS, local)
    assert [r["code"] for r in table] == ["BRL", "TRY"]   # Brazil cheaper in USD than Turkey
    brl = table[0]
    assert brl["usd_price"] == pytest.approx(23.9 / 5.7368)
    assert brl["valuation_pct"] == pytest.approx((23.9 / 5.7368 / 6.22 - 1) * 100)


def test_table_empty_without_us_price():
    assert prices.build_price_table(FX_ROWS, {"BRL": 23.9}) == []


def test_news_tie_in_uses_biggest_mover():
    local, _ = bigmac.read_price_csv(FIXTURE)
    line = prices.news_tie_in(prices.build_price_table(FX_ROWS, local), "Big Mac")
    assert line.startswith("The real weakened 1.32% overnight, so a Big Mac in Brazil got 1.31% cheaper")
    assert "($4.22 -> $4.17)" in line
