"""Inventory clearance strategy."""


def select(product):
    return {
        "strategy": "INVENTORY_CLEARANCE",
        "reason": ["high inventory aging"],
        "confidence": 0.8,
    }
