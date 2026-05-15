"""EWMA (Exponentially Weighted Moving Average) 异常检测模型

基于指数加权移动平均的单变量时序异常检测。
核心思想：计算 EWMA 基线，用滚动标准差缩放偏差，
当标准化绝对偏差超过阈值且连续 n_consecutive 个点时判定异常。

v1 scope：单变量（value 列），无方向输出，无特征工程。
"""

from __future__ import annotations

import hashlib
from importlib import import_module
from typing import Any, Dict, Optional

import mlflow
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from loguru import logger

from ..mlflow_utils import MLFlowUtils
from .base import BaseAnomalyModel, ModelRegistry


def _ewma_scores(
    values: NDArray[np.float64],
    alpha: float,
    scale_window: int,
) -> NDArray[np.float64]:
    """计算 EWMA 标准化绝对偏差分数。

    Args:
        values: 一维时序数值数组
        alpha: EWMA 平滑系数
        scale_window: 滚动标准差窗口大小

    Returns:
        标准化绝对偏差分数，值越大越异常
    """
    series = pd.Series(values, dtype=float)
    ewma_baseline = series.ewm(alpha=alpha, adjust=False).mean()
    deviation = series - ewma_baseline

    rolling_std = deviation.rolling(window=scale_window, min_periods=1).std()
    # 避免除零：用全局 std 的一个小分数兜底
    floor = float(deviation.std()) * 1e-6 if deviation.std() > 0 else 1e-12
    rolling_std = rolling_std.clip(lower=floor)

    scores = (deviation.abs() / rolling_std).to_numpy(dtype=float)
    # 前 scale_window 个点的 rolling_std 可能不稳定，用 0 填充 NaN
    scores = np.nan_to_num(scores, nan=0.0)
    return scores


def _apply_consecutive_filter(
    raw_labels: NDArray[np.int_],
    n_consecutive: int,
) -> NDArray[np.int_]:
    """仅保留连续 >= n_consecutive 个正标记的片段。

    Args:
        raw_labels: 二值标签数组
        n_consecutive: 最少连续异常点数

    Returns:
        过滤后的二值标签数组
    """
    if n_consecutive <= 1:
        return raw_labels.copy()

    result = np.zeros_like(raw_labels)
    n = len(raw_labels)
    i = 0
    while i < n:
        if raw_labels[i] == 1:
            j = i
            while j < n and raw_labels[j] == 1:
                j += 1
            if (j - i) >= n_consecutive:
                result[i:j] = 1
            i = j
        else:
            i += 1
    return result


def _labels_to_ranges(labels: NDArray[np.int_]) -> list[tuple[int, int]]:
    """将二值标签转换为连续正区间列表 [(start, end), ...]。"""
    ranges = []
    n = len(labels)
    i = 0
    while i < n:
        if labels[i] == 1:
            start = i
            while i < n and labels[i] == 1:
                i += 1
            ranges.append((start, i))
        else:
            i += 1
    return ranges


def _compute_drift_metrics(
    pred_labels: NDArray[np.int_],
    true_labels: NDArray[np.int_],
) -> Dict[str, float]:
    """计算基于区间一对一重叠的漂移精确率/召回率/F1。

    将预测和真实标签各自转换为连续正区间，
    按 IoU > 0（有重叠）进行一对一匹配（贪心），
    计算 drift_precision = matched_pred / total_pred,
    drift_recall = matched_true / total_true。
    """
    pred_ranges = _labels_to_ranges(pred_labels)
    true_ranges = _labels_to_ranges(true_labels)

    if not pred_ranges and not true_ranges:
        return {
            "drift_precision": 1.0,
            "drift_recall": 1.0,
            "drift_f1": 1.0,
            "num_pred_ranges": 0,
            "num_true_ranges": 0,
        }

    if not pred_ranges:
        return {
            "drift_precision": 0.0,
            "drift_recall": 0.0,
            "drift_f1": 0.0,
            "num_pred_ranges": 0,
            "num_true_ranges": len(true_ranges),
        }

    if not true_ranges:
        return {
            "drift_precision": 0.0,
            "drift_recall": 0.0,
            "drift_f1": 0.0,
            "num_pred_ranges": len(pred_ranges),
            "num_true_ranges": 0,
        }

    # 贪心一对一匹配：pred 区间与 true 区间有任何重叠即匹配
    matched_true = set()
    matched_pred = 0

    for ps, pe in pred_ranges:
        for idx, (ts, te) in enumerate(true_ranges):
            if idx in matched_true:
                continue
            # 检查重叠
            if ps < te and ts < pe:
                matched_pred += 1
                matched_true.add(idx)
                break

    drift_precision = matched_pred / len(pred_ranges) if pred_ranges else 0.0
    drift_recall = len(matched_true) / len(true_ranges) if true_ranges else 0.0
    drift_f1 = (
        float(2 * drift_precision * drift_recall / (drift_precision + drift_recall))
        if (drift_precision + drift_recall) > 0
        else 0.0
    )

    return {
        "drift_precision": drift_precision,
        "drift_recall": drift_recall,
        "drift_f1": drift_f1,
        "num_pred_ranges": len(pred_ranges),
        "num_true_ranges": len(true_ranges),
    }


@ModelRegistry.register("EWMA")
class EWMAModel(BaseAnomalyModel):
    """基于 EWMA 的单变量时序异常检测模型。

    分数语义：标准化绝对偏差（rolling_std 缩放），越大越异常。
    标签语义：score > threshold 且连续 >= n_consecutive 判定异常。
    """

    def __init__(
        self,
        alpha: float = 0.3,
        scale_window: int = 20,
        threshold: float = 3.0,
        n_consecutive: int = 3,
        scale_method: str = "rolling_std",
        severity_cap: float = 10.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            alpha=alpha,
            scale_window=scale_window,
            threshold=threshold,
            n_consecutive=n_consecutive,
            scale_method=scale_method,
            severity_cap=severity_cap,
            **kwargs,
        )
        self.alpha = float(alpha)
        self.scale_window = int(scale_window)
        self.threshold = float(threshold)
        self.n_consecutive = int(n_consecutive)
        self.scale_method = str(scale_method)
        self.severity_cap = float(severity_cap)
        self.feature_names_: list[str] | None = None
        self.n_samples_train_: int | None = None
        self.hyperopt_history_: list[dict[str, float | int | str]] = []

    def fit(
        self,
        train_data: pd.DataFrame,
        train_labels: pd.Series | NDArray[np.int_] | None = None,
        **kwargs: Any,
    ) -> "EWMAModel":
        """训练 EWMA 模型（记录训练元信息，EWMA 本身无状态拟合）。"""
        if not isinstance(train_data, pd.DataFrame):
            raise ValueError("train_data 必须是 pandas.DataFrame")
        if list(train_data.columns) != ["value"]:
            raise ValueError("EWMAModel 训练数据必须只包含 value 列")

        self.feature_names_ = train_data.columns.tolist()
        self.n_samples_train_ = len(train_data)
        self.threshold_ = self.threshold
        self.is_fitted = True

        logger.info(
            f"EWMA 模型训练完成: samples={self.n_samples_train_}, "
            f"alpha={self.alpha}, scale_window={self.scale_window}, "
            f"threshold={self.threshold}, n_consecutive={self.n_consecutive}"
        )
        return self

    def predict_proba(self, X: pd.DataFrame) -> NDArray[np.float64]:
        """返回标准化绝对偏差分数。"""
        self._check_fitted()
        self._validate_features(X)

        values = X["value"].to_numpy(dtype=float)
        return _ewma_scores(values, self.alpha, self.scale_window)

    def predict(self, X: pd.DataFrame) -> NDArray[np.int_]:
        """返回经 threshold + n_consecutive 过滤的二值标签。"""
        scores = self.predict_proba(X)
        raw_labels = (scores > self.threshold).astype(int)
        return _apply_consecutive_filter(raw_labels, self.n_consecutive)

    def evaluate_drifts(
        self,
        X: pd.DataFrame,
        labels: pd.Series | NDArray[np.int_],
        prefix: str = "",
    ) -> Dict[str, float]:
        """计算 EWMA 专属漂移段指标。"""
        pred_labels = self.predict(X)
        labels_array = (
            labels.to_numpy(dtype=int)
            if isinstance(labels, pd.Series)
            else labels.astype(int, copy=False)
        )

        metrics = _compute_drift_metrics(pred_labels, labels_array)

        if prefix:
            return {f"{prefix}_{k}": v for k, v in metrics.items()}
        return metrics

    def _build_search_space(self, search_space_config: Dict[str, Any]) -> Dict[str, Any]:
        from hyperopt import hp
    
        return {
            "alpha": hp.choice("alpha", search_space_config["alpha"]),
            "scale_window": hp.choice("scale_window", search_space_config["scale_window"]),
            "threshold": hp.choice("threshold", search_space_config["threshold"]),
            "n_consecutive": hp.choice("n_consecutive", search_space_config["n_consecutive"]),
        }
    
    def _decode_params(
        self, params_raw: Dict[str, Any], search_space_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        del search_space_config
        return {
            "alpha": float(params_raw["alpha"]),
            "scale_window": int(params_raw["scale_window"]),
            "threshold": float(params_raw["threshold"]),
            "n_consecutive": int(params_raw["n_consecutive"]),
        }
    
    def optimize_hyperparams(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame,
        train_labels: pd.Series | NDArray[np.int_],
        val_labels: pd.Series | NDArray[np.int_],
        config: Any,
    ) -> Dict[str, Any]:
        from hyperopt import STATUS_OK, Trials, fmin, space_eval, tpe
        from hyperopt.early_stop import no_progress_loss
    
        search_config = config.get_search_config()
        search_space = search_config["search_space"]
        max_evals = int(search_config.get("max_evals", 1))
        metric = search_config["metric"]
        early_stop_config = search_config.get("early_stopping", {})
        early_stop_enabled = bool(early_stop_config.get("enabled", True))
        patience = int(early_stop_config.get("patience", 10))
    
        resolved_scale_method = config.scale_method or self.scale_method
        resolved_severity_cap = (
            config.severity_cap if config.severity_cap is not None else self.severity_cap
        )
    
        if isinstance(train_labels, pd.Series):
            train_labels_array: NDArray[np.int_] = train_labels.to_numpy(dtype=int)
        else:
            train_labels_array = train_labels.astype(int, copy=False)
    
        if isinstance(val_labels, pd.Series):
            labels_array: NDArray[np.int_] = val_labels.to_numpy(dtype=int)
        else:
            labels_array = val_labels.astype(int, copy=False)
    
        drift_metrics = {"drift_precision", "drift_recall", "drift_f1"}
        best_score = [float("-inf")]
        best_params: Dict[str, Any] = {
            "alpha": self.alpha,
            "scale_window": self.scale_window,
            "threshold": self.threshold,
            "n_consecutive": self.n_consecutive,
        }
        eval_count = [0]
        failed_count = [0]
        trials = Trials()
        self.hyperopt_history_ = []
    
        grid_total = (
            len(search_space["alpha"])
            * len(search_space["scale_window"])
            * len(search_space["threshold"])
            * len(search_space["n_consecutive"])
        )
    
        logger.info(f"开始 EWMA 超参数优化 | max_evals={max_evals} | metric={metric}")
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
    
        space = self._build_search_space(search_space)
    
        def objective(params: Dict[str, Any]) -> Dict[str, Any]:
            eval_count[0] += 1
            current_eval = eval_count[0]
            decoded_params: Dict[str, Any] | None = None
    
            try:
                decoded_params = self._decode_params(params, search_space)
                alpha = decoded_params["alpha"]
                scale_window = decoded_params["scale_window"]
                threshold_val = decoded_params["threshold"]
                n_consecutive = decoded_params["n_consecutive"]
    
                candidate = EWMAModel(
                    alpha=alpha,
                    scale_window=scale_window,
                    threshold=threshold_val,
                    n_consecutive=n_consecutive,
                    scale_method=resolved_scale_method,
                    severity_cap=resolved_severity_cap,
                )
                candidate.fit(train_data)
    
                if metric in drift_metrics:
                    train_eval_metrics = candidate.evaluate_drifts(
                        train_data, train_labels_array
                    )
                    val_eval_metrics = candidate.evaluate_drifts(val_data, labels_array)
                    fallback_metric = "drift_f1"
                    trial_metric_keys = ["drift_precision", "drift_recall", "drift_f1"]
                else:
                    train_eval_metrics = candidate.evaluate(train_data, train_labels_array)
                    val_eval_metrics = candidate.evaluate(val_data, labels_array)
                    fallback_metric = "f1"
                    trial_metric_keys = ["precision", "recall", "f1", "auc"]
    
                score = float(val_eval_metrics.get(metric, val_eval_metrics[fallback_metric]))
                train_score = float(
                    train_eval_metrics.get(metric, train_eval_metrics[fallback_metric])
                )
                generalization_gap = train_score - score
                train_trial_metrics = MLFlowUtils.filter_numeric_metrics(
                    train_eval_metrics, trial_metric_keys
                )
                train_trial_metrics.setdefault(str(metric), float(train_score))
                trial_metrics = MLFlowUtils.filter_numeric_metrics(
                    val_eval_metrics, trial_metric_keys
                )
                trial_metrics.setdefault(str(metric), float(score))
                history_train_metrics = {
                    f"train_{key}": value for key, value in train_trial_metrics.items()
                }
    
                self.hyperopt_history_.append(
                    {
                        "trial": int(current_eval),
                        "metric": str(metric),
                        "score": float(score),
                        "train_score": float(train_score),
                        "generalization_gap": float(generalization_gap),
                        "alpha": float(alpha),
                        "scale_window": int(scale_window),
                        "threshold": float(threshold_val),
                        "n_consecutive": int(n_consecutive),
                        "status": "ok",
                        **trial_metrics,
                        **history_train_metrics,
                    }
                )
    
                logger.debug(
                    f"EWMA trial [{current_eval}/{max_evals}] | alpha={alpha} | sw={scale_window} | "
                    f"thr={threshold_val} | nc={n_consecutive} | train_metrics: "
                    f"{MLFlowUtils.format_metrics_for_log(train_trial_metrics, trial_metric_keys)} | "
                    f"val_metrics: {MLFlowUtils.format_metrics_for_log(trial_metrics, trial_metric_keys)} | "
                    f"generalization_gap={generalization_gap:.4f}"
                )
    
                if mlflow.active_run():
                    MLFlowUtils.log_metrics_batch(
                        train_trial_metrics,
                        prefix="hyperopt/train_",
                        step=current_eval,
                    )
                    MLFlowUtils.log_metrics_batch(
                        trial_metrics,
                        prefix="hyperopt/val_",
                        step=current_eval,
                    )
                    mlflow.log_metric(
                        "hyperopt/generalization_gap",
                        generalization_gap,
                        step=current_eval,
                    )
                    mlflow.log_metric("hyperopt/trial_score", score, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
    
                if score > best_score[0]:
                    best_score[0] = score
                    best_params.update(
                        {
                            "alpha": float(alpha),
                            "scale_window": int(scale_window),
                            "threshold": float(threshold_val),
                            "n_consecutive": int(n_consecutive),
                        }
                    )
                    logger.info(
                        f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] {metric}={score:.4f}"
                    )
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
    
                return {"loss": float(-score), "status": STATUS_OK}
    
            except Exception as exc:
                failed_count[0] += 1
                error_msg = str(exc)[:150]
                failure_record: dict[str, float | int | str] = {
                    "trial": int(current_eval),
                    "metric": str(metric),
                    "status": "failed",
                    "error": error_msg,
                }
                if decoded_params is not None:
                    failure_record.update(
                        {
                            "alpha": float(decoded_params["alpha"]),
                            "scale_window": int(decoded_params["scale_window"]),
                            "threshold": float(decoded_params["threshold"]),
                            "n_consecutive": int(decoded_params["n_consecutive"]),
                        }
                    )
                self.hyperopt_history_.append(failure_record)
                logger.error(f"EWMA trial [{current_eval}/{max_evals}] FAILED | error={error_msg}")
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                return {"loss": float("inf"), "status": STATUS_OK}
    
        best_params_raw = fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(config.random_state),
            verbose=False,
        )
    
best_params_actual = space_# FIX: 移除eval，改用安全方式
# space, best_params_raw)
        best_params = self._decode_params(best_params_actual, search_space)
    
        if mlflow.active_run():
            success_losses = [
                t["result"]["loss"]
                for t in trials.trials
                if t["result"]["status"] == "ok"
                and t["result"]["loss"] != float("inf")
            ]
            success_count = len(success_losses)
            actual_evals = len(trials.trials)
            is_early_stopped = actual_evals < max_evals
            summary_metrics = {
                "hyperopt_summary/total_evals": float(max_evals),
                "hyperopt_summary/actual_evals": float(actual_evals),
                "hyperopt_summary/grid_total_evals": float(grid_total),
                "hyperopt_summary/successful_evals": float(success_count),
                "hyperopt_summary/failed_evals": float(failed_count[0]),
                "hyperopt_summary/success_rate": (
                    success_count / actual_evals * 100 if actual_evals > 0 else 0.0
                ),
                "hyperopt_summary/best_score": best_score[0],
            }
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = (
                    1.0 if is_early_stopped else 0.0
                )
                summary_metrics["hyperopt_summary/patience_used"] = float(patience)
                if is_early_stopped:
                    summary_metrics["hyperopt_summary/time_saved_pct"] = (
                        ((max_evals - actual_evals) / max_evals * 100)
                        if max_evals > 0
                        else 0.0
                    )
            if success_losses:
                success_scores = [-loss for loss in success_losses]
                summary_metrics.update(
                    {
                        "hyperopt_summary/worst_score": min(success_scores),
                        "hyperopt_summary/mean_score": float(np.mean(success_scores)),
                        "hyperopt_summary/median_score": float(np.median(success_scores)),
                        "hyperopt_summary/std_score": float(np.std(success_scores)),
                    }
                )
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"EWMA Hyperopt summary | trials={actual_evals}/{max_evals} | best_{metric}={best_score[0]:.4f} | "
                f"best_params={best_params}"
            )
            mlflow.log_dict(
                {"trial_history": self.hyperopt_history_},
                "ewma_hyperopt_history.json",
            )
    
        self.alpha = float(best_params["alpha"])
        self.scale_window = int(best_params["scale_window"])
        self.threshold = float(best_params["threshold"])
        self.n_consecutive = int(best_params["n_consecutive"])
        self.config.update(best_params)
        return best_params

    def save_mlflow(self, artifact_path: str = "model") -> None:
        """保存模型到 MLflow。"""
        self._check_fitted()

        if mlflow.active_run():
            mlflow.log_dict(
                {
                    "model_type": "EWMA",
                    "alpha": self.alpha,
                    "scale_window": self.scale_window,
                    "threshold": self.threshold,
                    "n_consecutive": self.n_consecutive,
                    "scale_method": self.scale_method,
                    "severity_cap": self.severity_cap,
                    "score_semantics": "standardized_absolute_deviation",
                    "supports_runtime_threshold": True,
                    "feature_names": self.feature_names_,
                    "n_samples_train": self.n_samples_train_,
                },
                "model_metadata.json",
            )

        ewma_wrapper_module = import_module(
            "classify_anomaly_server.training.models.ewma_wrapper"
        )
        EWMAWrapper = ewma_wrapper_module.EWMAWrapper

        wrapped_model = EWMAWrapper(
            alpha=self.alpha,
            scale_window=self.scale_window,
            threshold=self.threshold,
            n_consecutive=self.n_consecutive,
            scale_method=self.scale_method,
            severity_cap=self.severity_cap,
        )

        import cloudpickle

        cloudpickle.dumps(wrapped_model)
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=wrapped_model,
        )

    def _validate_features(self, X: pd.DataFrame) -> None:
        if not isinstance(X, pd.DataFrame):
            raise ValueError("X 必须是 pandas.DataFrame")
        if self.feature_names_ is None or list(X.columns) != self.feature_names_:
            raise ValueError(
                f"特征列不匹配。期望: {self.feature_names_}, 实际: {list(X.columns)}"
            )
