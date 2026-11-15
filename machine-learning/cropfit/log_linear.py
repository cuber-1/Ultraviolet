from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin


class LogLinearCropFitRegressor(RegressorMixin, BaseEstimator):
    """Learn a multiplicative crop-suitability response in log space.

    The four inputs are temperature, water, pH, and solar range memberships.
    A zero membership is a structural zero; positive rows are fitted with
    ordinary least squares without pre-specifying any elasticity.
    """

    def fit(self, x: np.ndarray, y: np.ndarray) -> LogLinearCropFitRegressor:
        values = self._matrix(x)
        targets = np.asarray(y, dtype=np.float64)
        if targets.ndim != 1 or len(targets) != len(values):
            raise ValueError("Targets must be a one-dimensional array aligned with features.")
        if not np.all(np.isfinite(targets)):
            raise ValueError("Targets must be finite.")
        active = np.all(values > 0, axis=1)
        if not np.any(active) or np.any(targets[active] <= 0):
            raise ValueError("Positive feature rows require positive targets.")
        log_features = np.log(values[active])
        design = np.column_stack((np.ones(len(log_features)), log_features))
        solution, _, _, _ = np.linalg.lstsq(design, np.log(targets[active]), rcond=None)
        self.intercept_ = float(solution[0])
        self.coef_ = np.asarray(solution[1:], dtype=np.float64)
        self.n_features_in_ = int(values.shape[1])
        self.active_training_examples_ = int(np.sum(active))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if not hasattr(self, "coef_"):
            raise RuntimeError("Log-linear regressor is not fitted.")
        values = self._matrix(x)
        if values.shape[1] != self.n_features_in_:
            raise ValueError(f"Expected {self.n_features_in_} features, received {values.shape[1]}.")
        predictions = np.zeros(len(values), dtype=np.float64)
        active = np.all(values > 0, axis=1)
        predictions[active] = np.exp(self.intercept_ + np.log(values[active]) @ self.coef_)
        return np.clip(predictions, 0.0, 100.0)

    @staticmethod
    def _matrix(x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != 4:
            raise ValueError("Log-linear CropFit expects four membership features.")
        if not np.all(np.isfinite(values)) or np.any(values < 0):
            raise ValueError("Membership features must be finite and non-negative.")
        return values
