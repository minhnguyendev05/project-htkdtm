import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


class DemandBaseline:
    """Mo hinh du bao nhuong co ban dung Linear Regression."""

    def __init__(self):
        self.model = LinearRegression()

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)

    def evaluate(self, X, y):
        y_pred = self.predict(X)
        mae = mean_absolute_error(y, y_pred)
        rmse = mean_squared_error(y, y_pred, squared=False)
        return {"mae": mae, "rmse": rmse}


if __name__ == "__main__":
    X = np.array([[1], [2], [3], [4], [5]], dtype=float)
    y = np.array([2, 4, 6, 8, 10], dtype=float)
    model = DemandBaseline().fit(X, y)
    print("Du bao x=6:", model.predict(np.array([[6]])))
    print("Danh gia:", model.evaluate(X, y))
