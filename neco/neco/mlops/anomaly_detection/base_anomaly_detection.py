import abc
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from hyperopt import fmin, tpe, Trials, space_eval
from sklearn.metrics import (
    precision_recall_fscore_support,
    roc_auc_score,
    accuracy_score
)

from neco.mlops.anomaly_detection.feature_engineer import TimeSeriesFeatureEngineer
from neco.mlops.utils.mlflow_utils import MLFlowUtils
from neco.mlops.utils.ml_utils import MLUtils


class BaseAnomalyDetection(abc.ABC):
    """异常检测基类，提供通用的训练和预测功能"""

    def __init__(self):
        self.feature_engineer = None

    @abc.abstractmethod
    def build_model(self, train_params: dict):
        """构建模型实例"""
        pass

    def preprocess(self, df: pd.DataFrame, frequency: Optional[str] = None) -> Tuple[pd.DataFrame, List[str], Optional[str]]:
        """数据预处理：时间标准化、排序、缺失值填充"""
        if df is None:
            return None, [], frequency

        df = df.copy()

        # 标准化时间列并排序
        if not np.issubdtype(df["timestamp"].dtype, np.datetime64):
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

        # 设置时间索引，推断频率
        df = df.set_index("timestamp")
        if frequency is None:
            try:
                frequency = pd.infer_freq(df.index)
            except Exception as e:
                logger.warning(f"无法推断时间频率: {e}")
                frequency = None

        # 处理缺失值：时间插值 -> 前后填充 -> 中位数兜底
        value_series = df["value"].astype(float)
        value_series = value_series.interpolate(method="time", limit_direction="both")
        value_series = value_series.ffill().bfill()

        if value_series.isna().any():
            median_value = value_series.median() if not np.isnan(value_series.median()) else 0.0
            value_series = value_series.fillna(median_value)

        df["value"] = value_series
        df = df.reset_index()

        return df, ["value"], frequency

    def predict(
        self,
        data: pd.DataFrame,
        model_name: str,
        model_version: str = "latest",
        threshold: float = 0.5
    ) -> pd.DataFrame:
        """使用训练好的模型进行异常检测预测"""
        # 加载模型
        model = MLFlowUtils.load_model(model_name, model_version)
        
        # 数据预处理
        test_df, _, _ = self.preprocess(data, getattr(model, 'frequency', None))

        # 特征提取
        feature_engineer = TimeSeriesFeatureEngineer(tsfresh_params=None, n_jobs=4)
        X_test, _, _ = feature_engineer.extract_features(
            test_df,
            selected_features=model.feature_cols,
            extract_labels=False
        )
        
        # 预测
        anomaly_scores = MLUtils.get_prediction_scores(model, X_test)
        anomaly_labels = MLUtils.apply_threshold(anomaly_scores, threshold)

        return pd.DataFrame({
            'timestamp': test_df['timestamp'],
            'value': test_df['value'],
            'anomaly_probability': anomaly_scores,
            'anomaly_label': anomaly_labels
        })

    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        train_config: dict = {},
        max_evals: int = 50,
        mlflow_tracking_url: Optional[str] = None,
        experiment_name: str = "Default",
        tsfresh_params: Optional[Dict] = None,
        n_jobs: int = 0,
        primary_metric: str = "f1",
        positive_label: int = 1,
        decision_threshold: float = 0.5
    ):
        """训练异常检测模型"""
        MLFlowUtils.setup_experiment(mlflow_tracking_url, experiment_name)

        # 初始化特征工程器
        self.feature_engineer = TimeSeriesFeatureEngineer(
            tsfresh_params=tsfresh_params,
            n_jobs=n_jobs
        )

        # 数据预处理
        logger.info("📊 开始数据预处理...")
        train_df_prep, _, frequency = self.preprocess(train_dataframe, None)
        val_df_prep = self.preprocess(val_dataframe, frequency)[0]
        test_df_prep = self.preprocess(test_dataframe, frequency)[0]

        # 特征工程
        logger.info("🔧 开始特征工程...")
        X_train, y_train, feature_cols = self.feature_engineer.extract_features(train_df_prep)
        
        # 打印特征信息
        logger.info(f"✅ 特征提取完成，共找到 {len(feature_cols)} 个有效特征")
        logger.info(f"特征名称列表: {feature_cols[:10]}{'...' if len(feature_cols) > 10 else ''}")
        
        # 准备验证集
        logger.info("开始验证集特征工程...")
        X_val, y_val, _ = self.feature_engineer.extract_features(
            val_df_prep, selected_features=feature_cols
        )

        # 超参数优化
        logger.info(f"🔍 开始超参数优化，最大评估次数: {max_evals}")
        
        space = MLUtils.build_search_space(train_config)
        trials = Trials()
        train_scores_history = []
        val_scores_history = []
        
        def objective(params_raw):
            params = space_eval(space, params_raw)
            try:
                model = self.build_model(train_params=params)
                model.fit(X_train, y_train)

                # 计算验证分数
                val_scores = MLUtils.get_prediction_scores(model, X_val)
                val_score = MLUtils.calculate_metric_score(
                    y_val, val_scores, primary_metric, decision_threshold, positive_label
                )
                
                # 记录历史
                if len(train_scores_history) % 10 == 0:
                    train_scores = MLUtils.get_prediction_scores(model, X_train)
                    train_score = MLUtils.calculate_metric_score(
                        y_train, train_scores, primary_metric, decision_threshold, positive_label
                    )
                    logger.info(f"第 {len(train_scores_history)} 次评估 - 训练{primary_metric}: {train_score:.4f}, 验证{primary_metric}: {val_score:.4f}")
                
                train_scores_history.append(0)  # 占位符
                val_scores_history.append(val_score)
                
                return {"loss": -float(val_score), "status": "ok"}
            except Exception as e:
                logger.error(f"超参数评估失败: {e}")
                return {"loss": 1.0, "status": "ok"}

        best_params_raw = fmin(
            fn=objective, space=space, algo=tpe.suggest, max_evals=max_evals,
            trials=trials, rstate=np.random.default_rng(2025)
        )
        best_params = space_eval(space, best_params_raw)

        # 训练最终模型
        logger.info("🚀 训练最终模型...")
        best_model = self.build_model(train_params=best_params)
        best_model.fit(X_train, y_train)

        # 保存元数据
        best_model.feature_cols = feature_cols
        best_model.frequency = frequency
        best_model.tsfresh_params = tsfresh_params

        # 评估模型
        # 验证集评估
        val_scores = MLUtils.get_prediction_scores(best_model, X_val)
        val_metrics = {"auc": float(roc_auc_score(y_val, val_scores))}

        # 测试集评估
        X_test, y_test, _ = self.feature_engineer.extract_features(
            test_df_prep, selected_features=feature_cols
        )
        test_scores = MLUtils.get_prediction_scores(best_model, X_test)
        y_test_pred = MLUtils.apply_threshold(test_scores, decision_threshold)
        
        P, R, F1, _ = precision_recall_fscore_support(
            y_test, y_test_pred, pos_label=positive_label,
            average="binary", zero_division=0
        )
        
        test_metrics = {
            "auc": float(roc_auc_score(y_test, test_scores)),
            "precision": float(P),
            "recall": float(R), 
            "f1": float(F1),
            "accuracy": float(accuracy_score(y_test, y_test_pred))
        }

        # 记录到MLflow
        all_params = {
            **best_params,
            "max_evals": max_evals,
            "primary_metric": primary_metric,
            "decision_threshold": decision_threshold,
            "n_features": len(feature_cols),
            "train_samples": len(X_train)
        }
        
        MLFlowUtils.log_training_results(
            params=all_params,
            train_scores=train_scores_history,
            val_scores=val_scores_history,
            metric_name=primary_metric,
            val_metrics=val_metrics,
            test_metrics=test_metrics,
            model=best_model,
            model_name=model_name
        )

        logger.info(f"✅ 模型 {model_name} 训练完成")

        return {
            "best_params": best_params,
            "best_model": best_model,
            "feature_cols": feature_cols,
            "val_metrics": val_metrics,
            "test_metrics": test_metrics,
            "trials": trials
        }
