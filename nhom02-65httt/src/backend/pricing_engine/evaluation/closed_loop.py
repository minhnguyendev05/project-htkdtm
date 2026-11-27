"""Closed-loop evaluation."""
def evaluate(predicted, actual):
    return {"error": abs(predicted - actual)}
