"""
modules/prices.py: "Prices Around the World", the idea behind The Economist's Big Mac Index.

If exchange rates were "fair" (purchasing power parity, or PPP), a Big Mac would cost
the same in every country once converted to US dollars. When it's cheaper than in the
US, that currency looks UNDERVALUED; when it's pricier, OVERVALUED.

All the math, done in Python:
  Price in USD        = local price / today's USD/XXX rate
  Over/undervaluation = (price in USD / US price) - 1
  Implied PPP rate    = local price / US price
        (the exchange rate that WOULD make the Big Mac cost the same as in the US;
         compare it with today's actual rate)
"""

import config


# ---------------------------------------------------------------------------
# The formulas
# ---------------------------------------------------------------------------

def usd_price(local_price, usd_rate):
    """Convert a local price to dollars. Example: 23.9 BRL at USD/BRL 5.00 -> $4.78"""
    return local_price / usd_rate


def valuation_pct(price_in_usd, us_price):
    """
    % over (+) or under (-) valuation vs the US.
    Example: $4.78 vs $6.22 in the US -> -23.2% (undervalued)
    """
    return (price_in_usd / us_price - 1) * 100


def implied_ppp(local_price, us_price):
    """The USD/XXX rate that would make the item cost the same as in the US."""
    return local_price / us_price


def usd_price_change_pct(prev_close, rate):
    """
    How much the dollar price of something changed overnight, from the FX move alone.
    Local price stays the same, so: price_now / price_before - 1 = prev_close / rate - 1.
    Example: USD/BRL 5.00 -> 5.10 makes Brazilian things ~1.96% cheaper in dollars.
    """
    return (prev_close / rate - 1) * 100


# ---------------------------------------------------------------------------
# Building the table and the "connect it to the news" line
# ---------------------------------------------------------------------------

def build_price_table(fx_rows, local_prices):
    """
    Combine today's FX rows with an item's local prices.
    Returns rows sorted from most UNDERVALUED to most OVERVALUED.
    Countries without a price (or without an FX rate) are skipped.
    """
    us_price = local_prices.get("USD")
    if not us_price:
        return []

    names = {c["pair"]: c for c in config.CURRENCIES}
    table = []
    for fx_row in fx_rows:
        code = fx_row["pair"].split("/")[1]
        if code not in local_prices:
            continue
        local = local_prices[code]
        in_usd = usd_price(local, fx_row["rate"])
        info = names.get(fx_row["pair"], {})
        table.append({
            "pair": fx_row["pair"],
            "code": code,
            "country": info.get("country", code),
            "currency": info.get("currency", ""),
            "local_price": local,
            "rate": fx_row["rate"],
            "prev_close": fx_row["prev_close"],
            "fx_pct_change": fx_row["pct_change"],
            "usd_price": in_usd,
            "valuation_pct": valuation_pct(in_usd, us_price),
            "implied_ppp": implied_ppp(local, us_price),
        })

    table.sort(key=lambda r: r["valuation_pct"])
    return table


def news_tie_in(table, item_name, phrase=None):
    """
    One sentence linking today's biggest currency move to the item's dollar price.
    Example: "The real weakened 1.32% overnight, so a Big Mac in Brazil got 1.31%
    cheaper in US dollars ($4.22 -> $4.17)."
    `phrase` lets an item read naturally, e.g. "a liter of gasoline" (default: "a <item_name>").
    """
    if not table:
        return ""
    row = max(table, key=lambda r: abs(r["fx_pct_change"]))
    pct = row["fx_pct_change"]
    if pct == 0:
        return f"No tracked currency moved overnight, so {item_name} prices in dollars are unchanged."

    change = usd_price_change_pct(row["prev_close"], row["rate"])
    before = row["local_price"] / row["prev_close"]
    direction = "weakened" if pct > 0 else "strengthened"
    cheaper = "cheaper" if change < 0 else "more expensive"
    phrase = phrase or f"a {item_name}"
    return (f"The {row['currency']} {direction} {abs(pct):.2f}% overnight, so {phrase} in "
            f"{row['country']} got {abs(change):.2f}% {cheaper} in US dollars "
            f"(${before:,.2f} -> ${row['usd_price']:,.2f}).")
