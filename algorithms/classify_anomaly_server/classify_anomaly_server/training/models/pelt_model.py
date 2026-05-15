"""PELT changepoint 异常检测模型。"""

from __future__ import annotations

import hashlib
from importlib import import_module
from typing import Any, Optional

import mlflow
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from loguru import logger

from ..mlflow_utils import MLFlowUtils
from .base import BaseAnomalyModel, ModelRegistry
from .pelt_utils import (
    detect_changepoints,
    project_changepoints_to_point_labels,
    project_changepoints_to_point_scores,
)


@ModelRegistry.register("PELT")
class PELTModel(BaseAnomalyModel):
    """基于 ruptures PELT 的点级异常检测模型。"""

    def __init__(
        self,
        cost_model: str = "l2",
        pen: float = 10.0,
        min_size: int = 3,
        jump: int = 1,
        event_window: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            cost_model=cost_model,
            pen=pen,
            min_size=min_size,
            jump=jump,
            event_window=event_window,
            **kwargs,
        )
        self.cost_model = str(cost_model)
        self.pen = float(pen)
        self.min_size = int(min_size)
        self.jump = int(jump)
        self.event_window = int(event_window)
        self.feature_names_: list[str] | None = None
        self.n_samples_train_: int | None = None
        self.hyperopt_history_: list[dict[str, float | int | str]] = []
        self._changepoint_cache_key: str | None = None
        self._changepoint_cache: list[int] | None = None

    def fit(
        self,
        train_data: pd.DataFrame,
        train_labels: pd.Series | NDArray[np.int_] | None = None,
        **kwargs: Any,
    ) -> "PELTModel":
        if not isinstance(train_data, pd.DataFrame):
            raise ValueError("train_data 必须是 pandas.DataFrame")
        if list(train_data.columns) != ["value"]:
            raise ValueError("PELTModel 训练数据必须只包含 value 列")

        self.feature_names_ = train_data.columns.tolist()
        self.n_samples_train_ = len(train_data)
        self.threshold_ = None
        self._changepoint_cache_key = None
        self._changepoint_cache = None
        self.is_fitted = True

        logger.info(
            f"PELT 模型训练完成: samples={self.n_samples_train_}"
        )
        return self

    def predict(self, X: pd.DataFrame) -> NDArray[np.int_]:
        self._check_fitted()
        self._validate_features(X)

        changepoints = self.get_changepoints(X)
        return project_changepoints_to_point_labels(
            length=len(X),
            changepoints=changepoints,
            event_window=self.event_window,
        )

    def predict_proba(self, X: pd.DataFrame) -> NDArray[np.float64]:
        self._check_fitted()
        self._validate_features(X)

        changepoints = self.get_changepoints(X)
        return project_changepoints_to_point_scores(
            length=len(X),
            changepoints=changepoints,
            event_window=self.event_window,
        )

    def get_changepoints(self, X: pd.DataFrame) -> list[int]:
        """返回输入序列对应的 changepoint 索引。"""
        self._check_fitted()
        self._validate_features(X)

        signal = X["value"].to_numpy(dtype=float)
        cache_key = self._build_changepoint_cache_key(signal)
        if self._changepoint_cache_key == cache_key and self._changepoint_cache is not None:
            return list(self._changepoint_cache)

        changepoints = detect_changepoints(
            signal,
            cost_model=self.cost_model,
            min_size=self.min_size,
            jump=self.jump,
            pen=self.pen,
        )
        self._changepoint_cache_key = cache_key
        self._changepoint_cache = list(changepoints)
        return list(changepoints)

    def evaluate_changepoints(
        self,
        X: pd.DataFrame,
        labels: NDArray[np.int_] | pd.Series,
        prefix: str = "",
    ) -> dict[str, float]:
        """计算 PELT 专属 changepoint / event-window 指标。"""
        changepoints = self.get_changepoints(X)
        labels_array = (
            labels.to_numpy(dtype=int)
            if isinstance(labels, pd.Series)
            else labels.astype(int, copy=False)
        )

        labeled_points = int(labels_array.sum())
        matched_changepoints = sum(
            1
            for changepoint in changepoints
            if labels_array[
                max(0, changepoint - self.event_window) : min(
                    len(labels_array), changepoint + self.event_window + 1
                )
            ].any()
        )

        if labeled_points > 0:
            covered_points = sum(
                1
                for idx, value in enumerate(labels_array)
                if value == 1
                and any(
                    abs(idx - changepoint) <= self.event_window
                    for changepoint in changepoints
                )
            )
            changepoint_recall = covered_points / labeled_points
        else:
            changepoint_recall = 0.0

        changepoint_precision = (
            matched_changepoints / len(changepoints) if changepoints else 0.0
        )
        changepoint_f1 = (
            float(
                2
                * changepoint_precision
                * changepoint_recall
                / (changepoint_precision + changepoint_recall)
            )
            if (changepoint_precision + changepoint_recall) > 0
            else 0.0
        )

        metrics = {
            "num_changepoints": float(len(changepoints)),
            "num_labeled_points": float(labeled_points),
            "changepoint_precision": float(changepoint_precision),
            "changepoint_recall": float(changepoint_recall),
            "changepoint_f1": changepoint_f1,
        }

        if prefix:
            return {f"{prefix}_{key}": value for key, value in metrics.items()}
        return metrics

    def _build_search_space(self, search_space_config: dict[str, Any]) -> dict[str, Any]:
        from hyperopt import hp
    
        jump_values = search_space_config.get("jump", [self.jump])
        return {
            "pen": hp.choice("pen", search_space_config["pen"]),
            "min_size": hp.choice("min_size", search_space_config["min_size"]),
            "jump": hp.choice("jump", jump_values),
        }
    
    def _decode_params(
        self, params_raw: dict[str, Any], search_space_config: dict[str, Any]
    ) -> dict[str, Any]:
        del search_space_config
        return {
            "pen": float(params_raw["pen"]),
            "min_size": int(params_raw["min_size"]),
            "jump": int(params_raw["jump"]),
        }
    
    def optimize_hyperparams(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame,
        train_labels: NDArray[np.int_] | pd.Series,
        val_labels: NDArray[np.int_] | pd.Series,
        config: Any,
    ) -> dict[str, Any]:
        from hyperopt import STATUS_OK, Trials, fmin, space_eval, tpe
        from hyperopt.early_stop import no_progress_loss
    
        search_config = config.get_search_config()
        search_space = search_config["search_space"]
        max_evals = int(search_config.get("max_evals", 1))
        metric = search_config["metric"]
        early_stop_config = search_config.get("early_stopping", {})
        early_stop_enabled = bool(early_stop_config.get("enabled", True))
        patience = int(early_stop_config.get("patience", 10))
    
        best_score = [float("-inf")]
        best_params: dict[str, Any] = {
            "pen": self.pen,
            "min_size": self.min_size,
            "jump": self.jump,
        }
    
        jump_values = search_space.get("jump", [self.jump])
        resolved_cost_model = config.cost_model or self.cost_model
        resolved_event_window = (
            config.event_window if config.event_window is not None else self.event_window
        )
        if isinstance(train_labels, pd.Series):
            train_labels_array: NDArray[np.int_] = train_labels.to_numpy(dtype=int)
        else:
            train_labels_array = train_labels.astype(int, copy=False)
        if isinstance(val_labels, pd.Series):
            labels_array: NDArray[np.int_] = val_labels.to_numpy(dtype=int)
        else:
            labels_array = val_labels.astype(int, copy=False)
        changepoint_metrics = {
            "changepoint_precision",
            "changepoint_recall",
            "changepoint_f1",
        }
        eval_count = [0]
        failed_count = [0]
        trials = Trials()
        grid_total_evals = (
            len(search_space["pen"]) * len(search_space["min_size"]) * len(jump_values)
        )
    
        logger.info(f"开始超参数优化 | model=PELT | max_evals={max_evals} | metric={metric}")
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
    
        self.hyperopt_history_ = []
        space = self._build_search_space(search_space)
    
        def objective(params: dict[str, Any]) -> dict[str, Any]:
            eval_count[0] += 1
            current_eval = eval_count[0]
            decoded_params: dict[str, Any] | None = None
            try:
                decoded_params = self._decode_params(params, search_space)
                pen = decoded_params["pen"]
                min_size = decoded_params["min_size"]
                jump = decoded_params["jump"]
    
                candidate = PELTModel(
                    pen=pen,
                    min_size=min_size,
                    jump=jump,
                    cost_model=resolved_cost_model,
                    event_window=resolved_event_window,
                )
                candidate.fit(train_data)
    
                train_changepoint_eval = candidate.evaluate_changepoints(
                    train_data, train_labels_array
                )
                val_changepoint_eval = candidate.evaluate_changepoints(
                    val_data, labels_array
                )
    
                if metric in changepoint_metrics:
                    train_eval_metrics = train_changepoint_eval
                    metrics = val_changepoint_eval
                    fallback_metric = "changepoint_f1"
                else:
                    train_eval_metrics = candidate.evaluate(train_data, train_labels_array)
                    metrics = candidate.evaluate(val_data, labels_array)
                    fallback_metric = "f1"
    
                score = float(metrics.get(metric, metrics[fallback_metric]))
                train_score = float(
                    train_eval_metrics.get(metric, train_eval_metrics[fallback_metric])
                )
                generalization_gap = train_score - score
                train_num_changepoints = float(
                    train_changepoint_eval.get("num_changepoints", 0.0)
                )
                trial_num_changepoints = float(
                    val_changepoint_eval.get("num_changepoints", 0.0)
                )
                trial_metric_keys = (
                    [
                        "changepoint_precision",
                        "changepoint_recall",
                        "changepoint_f1",
                        "num_changepoints",
                    ]
                    if metric in changepoint_metrics
                    else ["precision", "recall", "f1", "auc", "num_changepoints"]
                )
                train_trial_metrics = MLFlowUtils.filter_numeric_metrics(train_eval_metrics)
                train_trial_metrics["num_changepoints"] = train_num_changepoints
                train_trial_metrics = MLFlowUtils.filter_numeric_metrics(
                    train_trial_metrics, trial_metric_keys
                )
                train_trial_metrics.setdefault(str(metric), float(train_score))
                trial_metrics = MLFlowUtils.filter_numeric_metrics(metrics)
                trial_metrics["num_changepoints"] = trial_num_changepoints
                trial_metrics = MLFlowUtils.filter_numeric_metrics(
                    trial_metrics, trial_metric_keys
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
                        "pen": float(pen),
                        "min_size": int(min_size),
                        "jump": int(jump),
                        "status": "ok",
                        **trial_metrics,
                        **history_train_metrics,
                    }
                )
    
                logger.debug(
                    f"PELT trial [{current_eval}/{max_evals}] | pen={pen} | min_size={min_size} | jump={jump} | train_metrics: "
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
                    best_params = {
                        "pen": float(pen),
                        "min_size": int(min_size),
                        "jump": int(jump),
                    }
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
                            "pen": float(decoded_params["pen"]),
                            "min_size": int(decoded_params["min_size"]),
                            "jump": int(decoded_params["jump"]),
                        }
                    )
                self.hyperopt_history_.append(failure_record)
                logger.error(
                    f"PELT trial [{current_eval}/{max_evals}] FAILED | error={error_msg}"
                )
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
    
        if self.hyperopt_history_ and all(
            float(item.get("num_changepoints", 0.0)) == 0.0
            for item in self.hyperopt_history_
            if item.get("status") == "ok"
        ):
            logger.warning(
                "PELT 超参数搜索未检测到任何 changepoint: all trials produced num_changepoints=0"
            )
    
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
                "hyperopt_summary/grid_total_evals": float(grid_total_evals),
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
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"PELT Hyperopt summary | trials={actual_evals}/{max_evals} | best_{metric}={best_score[0]:.4f} | "
                f"best_params={best_params}"
            )
            mlflow.log_dict(
                {"trial_history": self.hyperopt_history_},
                "pelt_hyperopt_history.json",
            )
    
        self.pen = float(best_params["pen"])
        self.min_size = int(best_params["min_size"])
        self.jump = int(best_params["jump"])
        self.config.update(best_params)
        return best_params

    def save_mlflow(self, artifact_path: str = "model") -> None:
        self._check_fitted()

        if mlflow.active_run():
            mlflow.log_dict(
                {
                    "model_type": "PELT",
                    "cost_model": self.cost_model,
                    "pen": self.pen,
                    "min_size": self.min_size,
                    "jump": self.jump,
                    "event_window": self.event_window,
                    "score_semantics": "binary_window",
                    "supports_runtime_threshold": False,
                    "threshold_semantics": "legacy_compatibility_only",
                    "feature_names": self.feature_names_,
                    "n_samples_train": self.n_samples_train_,
                },
                "model_metadata.json",
            )

        pelt_wrapper_module = import_module(
            "classify_anomaly_server.training.models.pelt_wrapper"
        )
        PELTWrapper = pelt_wrapper_module.PELTWrapper

        wrapped_model = PELTWrapper(
            cost_model=self.cost_model,
            pen=self.pen,
            min_size=self.min_size,
            jump=self.jump,
            event_window=self.event_window,
        )

        import cloudpickle

        cloudpickle.dumps(wrapped_model)
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=wrapped_model,
        )

    def _build_changepoint_cache_key(self, signal: NDArray[np.float64]) -> str:
        hasher = hashlib.blake2b(digest_size=16)
        hasher.update(signal.tobytes())
        hasher.update(str(self.cost_model).encode())
        hasher.update(str(self.pen).encode())
        hasher.update(str(self.min_size).encode())
        hasher.update(str(self.jump).encode())
        hasher.update(str(self.event_window).encode())
        return hasher.hexdigest()

    def _validate_features(self, X: pd.DataFrame) -> None:
        if not isinstance(X, pd.DataFrame):
            raise ValueError("X 必须是 pandas.DataFrame")
        if self.feature_names_ is None or list(X.columns) != self.feature_names_:
            raise ValueError(
                f"特征列不匹配。期望: {self.feature_names_}, 实际: {list(X.columns)}"
            )
