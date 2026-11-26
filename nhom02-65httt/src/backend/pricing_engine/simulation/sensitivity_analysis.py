"""Sensitivity analysis."""
def sensitivity(prices, fn):
    return [{"price": p, "value": fn(p)} for p in prices]
"""