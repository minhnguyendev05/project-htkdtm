"""Adaptive strategy switching."""
def should_switch(current, proposed, threshold=0.2):
    return proposed != current
