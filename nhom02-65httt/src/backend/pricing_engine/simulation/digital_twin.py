"""Digital twin simulation."""
def simulate(prices, demand_fn):
    return [{"price": p, "demand": demand_fn(p)} for p in prices]
"""