"""Objective function."""
def score(profit, revenue, competitive, inventory, risk, weights):
    return (weights["profit"]*profit + weights["revenue"]*revenue +
            weights["competitive"]*competitive + weights["inventory"]*inventory -
            weights["risk"]*risk)
