"""Product state analysis."""
def analyze(product):
    return {"state": "STABLE", "inventory_days": product.get("inventory_days", 0)}
