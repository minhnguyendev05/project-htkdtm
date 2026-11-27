"""Scenario engine."""
def run_scenarios(scenarios, fn):
    return {name: fn(s) for name, s in scenarios.items()}
