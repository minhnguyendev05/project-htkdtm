"""Optimizer."""
def optimize(candidates, score_fn):
    return max(candidates, key=score_fn)
"""