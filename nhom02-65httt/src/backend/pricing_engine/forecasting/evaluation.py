"""Forecast evaluation metrics."""

import math


def mae(y_true, y_pred):
    return sum(abs(a - b) for a, b in zip(y_true, y_pred, strict=False)) / len(y_true)


def rmse(y_true, y_pred):
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(y_true, y_pred, strict=False)) / len(y_true)
    )
