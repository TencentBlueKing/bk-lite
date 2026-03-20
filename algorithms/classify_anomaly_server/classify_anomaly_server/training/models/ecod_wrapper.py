"""ECOD 模型的 MLflow 推理包装器

此文件包含 ECOD 模型的 MLflow 包装器，用于模型推理服务。
"""

from typing import Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from scipy.stats import skew


class ECODWrapper(mlflow.pyfunc.PythonModel):
    """ECOD 模型的 MLflow 包装器

    用于 MLflow 模型保存和推理服务。
    """

    def __init__(self, model, feature_names: list, threshold: float):
        """初始化包装器

        Args:
            model: 训练好的 ECOD 模型（pyod.models.ecod.ECOD）
            feature_names: 特征名称列表
            threshold: 异常阈值
        """
        self.model = model
        self.feature_names = feature_names
        self.threshold = threshold
        self.train_reference = getattr(model, "X_train", None)
        self.train_sorted = None
        self.train_skew_sign = None

        if self.train_reference is not None:
            self.train_reference = np.asarray(self.train_reference, dtype=float)
            self.train_sorted = np.sort(self.train_reference, axis=0)
            self.train_skew_sign = np.sign(
                np.nan_to_num(skew(self.train_reference, axis=0), nan=0.0)
            )

        logger.debug(
            f"ECODWrapper 初始化: features={len(feature_names)}, threshold={threshold}"
        )

    def predict(self, context, model_input) -> dict:
        """预测接口

        Args:
            context: MLflow context
            model_input: 字典格式 {'data': pd.Series, 'threshold': float (可选)}

        Returns:
            字典格式 {'labels': [0,1,...], 'scores': [0.1,0.9,...]}
        """
        # 解析输入
        data, threshold = self._parse_input(model_input)

        # 转换为 DataFrame（内部处理）
        if isinstance(data, pd.Series):
            df = pd.DataFrame({"value": data.values}, index=data.index)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            raise ValueError(
                f"data 必须是 pd.Series 或 pd.DataFrame，实际类型: {type(data)}"
            )

        # 检查特征（如果是 DataFrame 且指定了特征名）
        if isinstance(data, pd.DataFrame) and df.shape[1] != len(self.feature_names):
            raise ValueError(
                f"特征数量不匹配: 期望 {len(self.feature_names)}，实际 {df.shape[1]}"
            )

        # 预测异常分数（基于训练分布冻结参考，避免当前 batch 影响分数）
        scores = self._decision_function_against_train_reference(df)

        # 计算归一化严重度（基于阈值线性映射，用于展示，不是真实概率）
        anomaly_severity = np.minimum(scores / (threshold * 2), 1.0)

        # 根据阈值判断异常
        predictions = (scores > threshold).astype(int)

        # 返回字典格式（与 DummyModel 一致）
        return {
            "labels": predictions.tolist(),
            "scores": scores.tolist(),
            "anomaly_severity": anomaly_severity.tolist(),
        }

    def _parse_input(self, model_input) -> tuple:
        """解析输入数据

        Args:
            model_input: 字典格式 {'data': pd.Series, 'threshold': float (可选)}

        Returns:
            (data, threshold) 元组
        """
        if isinstance(model_input, dict):
            data = model_input.get("data")
            threshold = model_input.get("threshold", self.threshold)

            if data is None:
                raise ValueError("输入必须包含 'data' 字段")

            return data, threshold
        else:
            raise ValueError("输入格式错误，需要 dict 类型")

    def _decision_function_against_train_reference(
        self, df: pd.DataFrame
    ) -> np.ndarray:
        """基于训练分布计算稳定的 ECOD 异常分数。

        PyOD 原生 ECOD 在推理时会把 X_train 与当前 batch 拼接后重算 ECDF，
        导致同一个值在不同 batch 里的分数不稳定。这里改为只参考训练分布。
        """
        if (
            self.train_reference is None
            or self.train_sorted is None
            or self.train_skew_sign is None
        ):
            logger.warning("缺少训练参考分布，回退到 PyOD 原生 decision_function")
            return self.model.decision_function(df)

        values = df.to_numpy(dtype=float)
        if values.shape[1] != self.train_reference.shape[1]:
            raise ValueError(
                f"特征数量不匹配: 训练参考 {self.train_reference.shape[1]}，"
                f"实际 {values.shape[1]}"
            )

        n_train = self.train_reference.shape[0]
        min_prob = 1.0 / n_train

        left_counts = np.empty_like(values, dtype=float)
        right_counts = np.empty_like(values, dtype=float)

        for idx in range(values.shape[1]):
            sorted_col = self.train_sorted[:, idx]
            left_counts[:, idx] = np.searchsorted(
                sorted_col, values[:, idx], side="right"
            )
            right_counts[:, idx] = n_train - np.searchsorted(
                sorted_col, values[:, idx], side="left"
            )

        left_ecdf = np.clip(left_counts / n_train, min_prob, 1.0)
        right_ecdf = np.clip(right_counts / n_train, min_prob, 1.0)

        u_l = -np.log(left_ecdf)
        u_r = -np.log(right_ecdf)
        u_skew = u_l * -1 * np.sign(self.train_skew_sign - 1) + u_r * np.sign(
            self.train_skew_sign + 1
        )

        outlier_scores = np.maximum(u_l, u_r)
        outlier_scores = np.maximum(u_skew, outlier_scores)

        return outlier_scores.sum(axis=1).ravel()
