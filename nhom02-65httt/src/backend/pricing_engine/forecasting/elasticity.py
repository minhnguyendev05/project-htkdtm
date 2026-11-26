"""Price elasticity analysis."""
def elasticity(price_before, qty_before, price_after, qty_after):
    if price_before == 0:
        return None
    pct_p = (price_after - price_before) / price_before
    pct_q = (qty_after - qty_before) / qty_before if qty_before else 0
    return pct_q / pct_p if pct_p else None
"""