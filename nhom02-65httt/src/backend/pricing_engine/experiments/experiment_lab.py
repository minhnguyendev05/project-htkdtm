"""Experiment lab."""
def compare(methods, data):
    return {m: (sum(data) / len(data)) for m in methods}
