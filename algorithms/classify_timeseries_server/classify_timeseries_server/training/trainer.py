"""通用时间序列训练器

支持多种模型的统一训练流程，包括：
- 数据加载和预处理
- 动态模型选择
- 超参数优化
- 模型训练和评估
- MLflow 集成
"""

from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import mlflow
from pathlib import Path
from loguru import logger

from .config.loader import TrainingConfig
from .models.base import ModelRegistry, BaseTimeSeriesModel
from .preprocessing import TimeSeriesPreprocessor
from .data_loader import load_dataset
from .mlflow_utils import MLFlowUtils


class UniversalTrainer:
    """通用时间序列训练器

    核心功能：
    1. 配置驱动的训练流程
    2. 动态模型加载（通过 ModelRegistry）
    3. 完整的数据处理 Pipeline
    4. 可选的超参数优化
    5. MLflow 实验跟踪

    使用示例：
        config = TrainingConfig("train.json")
        trainer = UniversalTrainer(config)
        result = trainer.train("data.csv")
    """

    def __init__(self, config: TrainingConfig):
        """初始化训练器

        Args:
            config: 训练配置对象
        """
        self.config = config
        self.model = None
        self.preprocessor = None
        self.frequency = None

        logger.info(f"训练器初始化 - 模型类型: {config.model_type}")

    def train(self, dataset_path: str) -> Dict[str, Any]:
        """执行完整训练流程

        数据加载支持两种模式：
        - 目录模式：dataset_path 为目录，自动查找 train_data.csv/val_data.csv/test_data.csv
        - 文件模式：dataset_path 为单个CSV文件，自动按固定比例(0.2/0.1)划分

        Args:
            dataset_path: 数据集路径（目录或单个文件）

        Returns:
            训练结果字典，包含：
            - model: 训练好的模型
            - test_metrics: 测试集评估指标
            - val_metrics: 验证集评估指标（如果有）
            - run_id: MLflow run ID
            - frequency: 推断的时间频率
            - best_params: 最优超参数（如果进行了优化）
        """
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.model_type}")
        logger.info("=" * 60)

        # 1. 设置 MLflow
        self._setup_mlflow()

        # 2. 加载数据
        train_df, val_df, test_df = self._load_data(dataset_path)

        # 3. 数据预处理
        train_data, val_data, test_data = self._preprocess_data(
            train_df, val_df, test_df
        )

        # 4. 创建模型实例
        self.model = self._create_model()

        # 5. 开始 MLflow run
        with mlflow.start_run(run_name=self.config.mlflow_run_name) as run:
            try:
                # 记录配置
                self._log_config()

                # 6. 超参数优化（默认启用）
                best_params = None
                if val_data is not None:
                    best_params = self._optimize_hyperparams(train_data, val_data)
                    mlflow.log_params(best_params)

                # 7. 训练模型
                self._train_model(train_data, val_data)

                # 7.5. 评估训练数据拟合度（样本内评估）
                # 注意: fit()默认使用merge_val=True,即train+val一起训练
                # 因此这里评估的是整个训练数据(train+val)的拟合度
                val_metrics = None
                if val_data is not None:
                    final_train_data = pd.concat([train_data, val_data])
                    logger.info("评估最终训练数据拟合度（train+val样本内评估）...")
                    final_train_metrics = self.model.evaluate(
                        final_train_data, is_in_sample=True
                    )
                    # 过滤掉内部数据（_开头的键，如 _predictions, _y_true）
                    metrics_to_log = {
                        k: v
                        for k, v in final_train_metrics.items()
                        if not k.startswith("_")
                    }
                    mlflow.log_metrics(
                        {f"final_train_{k}": v for k, v in metrics_to_log.items()}
                    )
                    MLFlowUtils.log_params_batch(
                        {
                            "final_train_samples": len(final_train_data),
                            "final_train_merge_val": True,
                            "final_train_eval_mode": "in_sample",
                        }
                    )
                    logger.info(f"最终训练数据拟合度评估完成: {final_train_metrics}")
                else:
                    # 无验证集,只评估训练集
                    logger.info("评估训练集拟合度（样本内评估）...")
                    train_metrics = self.model.evaluate(train_data, is_in_sample=True)
                    # 过滤掉内部数据（_开头的键，如 _predictions, _y_true）
                    metrics_to_log = {
                        k: v for k, v in train_metrics.items() if not k.startswith("_")
                    }
                    mlflow.log_metrics(
                        {f"train_{k}": v for k, v in metrics_to_log.items()}
                    )
                    logger.info(f"训练集拟合度评估完成: {train_metrics}")

                # 9. 评估测试集（从训练+验证集末尾预测）
                test_metrics = self._evaluate_model_on_test(
                    train_data=train_data, val_data=val_data, test_data=test_data
                )
                mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})

                # 10. 保存模型到 MLflow
                model_uri = self._save_model_to_mlflow()

                # 11. 注册模型到 MLflow Model Registry
                self._register_model(model_uri)

                result = {
                    "model": self.model,
                    "test_metrics": test_metrics,
                    "val_metrics": val_metrics,
                    "run_id": run.info.run_id,
                    "frequency": self.frequency,
                    "best_params": best_params,
                }

                logger.info("=" * 60)
                logger.info("训练完成")
                logger.info(f"测试集指标: {test_metrics}")
                logger.info(f"MLflow Run ID: {run.info.run_id}")
                logger.info("=" * 60)

                return result

            except Exception as e:
                logger.error(f"训练过程出错: {e}")
                MLFlowUtils.log_params_batch({"status": "failed", "error": str(e)})
                raise

    def _setup_mlflow(self):
        """设置 MLflow 实验"""
        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name

        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)

        logger.info(f"MLflow 实验: {experiment_name}")
        if tracking_uri:
            logger.info(f"MLflow URI: {tracking_uri}")

    def _load_data(
        self, dataset_path: str
    ) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """加载数据集（支持目录模式和文件模式）

        目录模式：
            - 必须包含：train_data.csv
            - 可选包含：val_data.csv, test_data.csv
            - 宽松模式：如缺失验证集/测试集，后续自动划分

        文件模式：
            - 加载单个CSV文件
            - 返回 (df, None, None)，后续自动划分

        Args:
            dataset_path: 数据集路径（目录或文件）

        Returns:
            (训练集, 验证集, 测试集)

        Raises:
            ValueError: 路径既不是文件也不是目录
            FileNotFoundError: 目录模式下未找到 train_data.csv
        """
        import os

        if os.path.isdir(dataset_path):
            # 目录模式
            logger.info(f"📁 检测到目录模式: {dataset_path}")

            train_path = os.path.join(dataset_path, "train_data.csv")
            if not os.path.exists(train_path):
                raise FileNotFoundError(
                    f"目录模式下未找到训练数据文件: {train_path}\n"
                    f"目录中必须包含 train_data.csv"
                )

            train_df = load_dataset(train_path)
            logger.info(f"✓ 训练集: {len(train_df)} 条记录 (train_data.csv)")

            # 可选的验证集
            val_df = None
            val_path = os.path.join(dataset_path, "val_data.csv")
            if os.path.exists(val_path):
                val_df = load_dataset(val_path)
                logger.info(f"✓ 验证集: {len(val_df)} 条记录 (val_data.csv)")
            else:
                logger.info("⚠ 未找到 val_data.csv，将从训练集自动划分")

            # 可选的测试集
            test_df = None
            test_path = os.path.join(dataset_path, "test_data.csv")
            if os.path.exists(test_path):
                test_df = load_dataset(test_path)
                logger.info(f"✓ 测试集: {len(test_df)} 条记录 (test_data.csv)")
            else:
                logger.info("⚠ 未找到 test_data.csv，将从训练集自动划分")

            return train_df, val_df, test_df

        elif os.path.isfile(dataset_path):
            # 文件模式
            logger.info(f"📄 检测到文件模式: {dataset_path}")
            df = load_dataset(dataset_path)
            logger.info(f"✓ 加载数据: {len(df)} 条记录")
            logger.info("ℹ 将按固定比例自动划分（测试集 0.2，验证集 0.1）")
            return df, None, None

        else:
            raise ValueError(
                f"无效的数据集路径: {dataset_path}\n"
                f"路径必须是以下之一：\n"
                f"  1. 包含 train_data.csv 的目录\n"
                f"  2. 单个 CSV 文件"
            )

    def _preprocess_data(
        self,
        train_df: pd.DataFrame,
        val_df: Optional[pd.DataFrame],
        test_df: Optional[pd.DataFrame],
    ) -> Tuple[pd.Series, Optional[pd.Series], pd.Series]:
        """数据预处理（清洗 + 自动划分）

        如未提供测试集/验证集，从训练集按固定比例自动划分（测试集0.2，验证集0.1）。

        Args:
            train_df: 训练数据框（单文件模式时包含完整数据）
            val_df: 验证数据框（可选）
            test_df: 测试数据框（可选）

        Returns:
            (训练序列, 验证序列, 测试序列)
        """
        logger.info("数据预处理（清洗）...")

        # 1. 获取预处理配置（只有清洗相关参数）
        preprocess_config = self.config.get("preprocessing", default={})

        # 2. 创建预处理器（简化：只需清洗参数）
        self.preprocessor = TimeSeriesPreprocessor(
            max_missing_ratio=preprocess_config.get("max_missing_ratio", 0.3),
            interpolation_limit=preprocess_config.get("interpolation_limit", 3),
            handle_missing=preprocess_config.get("handle_missing", "interpolate"),
        )

        logger.info(f"预处理配置: {preprocess_config}")

        # 3. 清洗所有数据集（无状态，直接调用）
        train_data, frequency = self.preprocessor.clean(train_df.copy())
        self.frequency = frequency
        logger.info(
            f"训练集清洗完成: {len(train_data)} 个数据点, 频率: {frequency or '未知'}"
        )

        # 验证集
        val_data = None
        if val_df is not None:
            val_data, _ = self.preprocessor.clean(val_df.copy(), frequency)
            logger.info(f"验证集清洗完成: {len(val_data)} 个数据点")

        # 测试集或从训练集分割
        if test_df is not None:
            test_data, _ = self.preprocessor.clean(test_df.copy(), frequency)
            logger.info(f"测试集清洗完成: {len(test_data)} 个数据点")
        else:
            # 从训练集分割测试集
            test_size = self.config.test_size
            split_point = int(len(train_data) * (1 - test_size))
            test_data = train_data[split_point:]
            train_data = train_data[:split_point]
            logger.info(
                f"从训练集分割测试集: 训练={len(train_data)}, 测试={len(test_data)}"
            )

            # 如果需要验证集，从训练集再分割
            if val_data is None and self.config.validation_size > 0:
                val_size = self.config.validation_size
                val_split = int(len(train_data) * (1 - val_size))
                val_data = train_data[val_split:]
                train_data = train_data[:val_split]
                logger.info(
                    f"从训练集分割验证集: 训练={len(train_data)}, 验证={len(val_data)}"
                )

        # 记录数据基本信息和统计特征到 MLflow
        if mlflow.active_run():
            # 收集所有参数到字典
            data_params = {}

            # 数据基本信息
            if isinstance(train_data.index, pd.DatetimeIndex):
                data_params["train_start_date"] = str(train_data.index[0])
                data_params["train_end_date"] = str(train_data.index[-1])
                if val_data is not None and isinstance(
                    val_data.index, pd.DatetimeIndex
                ):
                    data_params["val_start_date"] = str(val_data.index[0])
                    data_params["val_end_date"] = str(val_data.index[-1])
                if test_data is not None and isinstance(
                    test_data.index, pd.DatetimeIndex
                ):
                    data_params["test_start_date"] = str(test_data.index[0])
                    data_params["test_end_date"] = str(test_data.index[-1])

            data_params["train_samples"] = len(train_data)
            if val_data is not None:
                data_params["val_samples"] = len(val_data)
            if test_data is not None:
                data_params["test_samples"] = len(test_data)

            try:
                freq = (
                    pd.infer_freq(train_data.index)
                    if isinstance(train_data.index, pd.DatetimeIndex)
                    else None
                )
                data_params["data_frequency"] = str(freq) if freq else "unknown"
            except:
                data_params["data_frequency"] = "unknown"

            # 批量记录参数
            MLFlowUtils.log_params_batch(data_params)

            # 数据统计特征
            mlflow.log_metric("data_mean", float(train_data.mean()))
            mlflow.log_metric("data_std", float(train_data.std()))
            mlflow.log_metric("data_min", float(train_data.min()))
            mlflow.log_metric("data_max", float(train_data.max()))
            mlflow.log_metric("data_median", float(train_data.median()))
            mlflow.log_metric("data_range", float(train_data.max() - train_data.min()))

            logger.info("数据信息已记录到 MLflow")

        logger.info("数据预处理完成")

        return train_data, val_data, test_data

    def _create_model(self) -> BaseTimeSeriesModel:
        """创建模型实例

        Returns:
            模型实例

        Raises:
            ValueError: 模型类型未注册
        """
        model_type = self.config.model_type

        # 从注册表获取模型类
        model_class = ModelRegistry.get(model_type)

        # 获取模型参数
        model_params = self.config.get_model_params()

        # 获取特征工程配置
        fe_config = self.config.get_feature_engineering_config()

        logger.info(f"创建模型: {model_type}")
        logger.debug(f"模型参数: {model_params}")
        if fe_config:
            logger.debug(f"特征工程配置: {fe_config}")

        # 实例化模型
        model = model_class(**model_params, feature_engineering_config=fe_config)

        return model

    def _optimize_hyperparams(
        self, train_data: pd.Series, val_data: pd.Series
    ) -> Dict[str, Any]:
        """超参数优化

        Args:
            train_data: 训练数据
            val_data: 验证数据

        Returns:
            最优超参数字典
        """
        logger.info("开始超参数优化...")

        # 检查模型是否支持超参数优化
        if not hasattr(self.model, "optimize_hyperparams"):
            logger.warning(f"{self.config.model_type} 模型不支持超参数优化，跳过")
            return {}

        # 执行优化
        best_params = self.model.optimize_hyperparams(train_data, val_data, self.config)

        logger.info(f"超参数优化完成: {best_params}")

        return best_params

    def _train_model(self, train_data: pd.Series, val_data: Optional[pd.Series]):
        """训练模型

        Args:
            train_data: 训练数据
            val_data: 验证数据（可选）
        """
        logger.info("开始训练模型...")

        self.model.fit(train_data, val_data)

        logger.info("模型训练完成")

    def _evaluate_model_on_test(
        self, train_data: pd.Series, val_data: Optional[pd.Series], test_data: pd.Series
    ) -> Dict[str, float]:
        """评估测试集（从训练+验证数据末尾预测）

        Args:
            train_data: 训练数据（原始尺度）
            val_data: 验证数据（原始尺度，可选）
            test_data: 测试数据（原始尺度）

        Returns:
            评估指标字典
        """
        logger.info("评估测试集（从训练+验证集末尾预测）...")

        # 如果有验证集，需要在训练+验证数据上更新模型预测起点
        if val_data is not None:
            logger.info("在训练+验证集上更新模型预测起点...")

            # 合并训练和验证数据
            combined_data = pd.concat([train_data, val_data])
            logger.info(
                f"合并数据: 训练({len(train_data)}) + 验证({len(val_data)}) = {len(combined_data)}"
            )

            # 更新模型的预测起点（不重新训练参数，只更新起点）
            self._update_model_for_prediction(combined_data)

            # 使用合并数据进行可视化
            history_data = combined_data
        else:
            history_data = train_data

        # 使用模型的 evaluate() 方法进行评估（让模型自己决定评估策略）
        metrics = self.model.evaluate(test_data, mode="auto", is_in_sample=False)

        # 提取预测值用于可视化（使用 pop 避免污染指标字典）
        predictions = metrics.pop("_predictions")
        y_true = metrics.pop("_y_true", test_data.values)
        # 清理其他内部数据
        metrics.pop("_mode", None)
        metrics.pop("_is_in_sample", None)

        logger.info(f"测试集评估完成: {metrics}")

        # 绘制可视化图表
        if mlflow.active_run():
            from .mlflow_utils import MLFlowUtils

            # 1. 预测结果对比图
            MLFlowUtils.plot_prediction_results(
                train_data=history_data,
                test_data=test_data,
                predictions=predictions,
                title=f"{self.config.model_type.upper()} 预测结果",
                artifact_name=f"{self.config.model_type}_prediction",
                metrics=metrics,
            )

            # 2. 残差分析图
            residuals = y_true - predictions
            MLFlowUtils.plot_residuals_analysis(
                residuals=residuals,
                title=f"{self.config.model_type.upper()} 残差分析",
                artifact_name=f"{self.config.model_type}_residuals",
            )

            logger.info("预测可视化图表已上传到 MLflow")

        return metrics

    def _update_model_for_prediction(self, data: pd.Series):
        """更新模型的预测起点（不重新训练参数）

        GradientBoosting: 更新历史数据，确保有完整上下文提取特征

        Args:
            data: 用作预测起点的历史数据（训练集+验证集的合并）
        """
        model_type = self.config.model_type

        if model_type == "GradientBoosting":
            # GradientBoosting: 更新历史上下文
            # 理由：
            # 1. GB 使用递归预测，需要完整的历史序列
            # 2. 特征工程需要从历史中提取滞后特征、滚动特征等
            # 3. 模型参数不变，只更新用于预测的数据上下文
            from .models.gradient_boosting_model import GradientBoostingModel

            if isinstance(self.model, GradientBoostingModel):
                logger.info(f"更新 GradientBoosting 预测起点，数据长度: {len(data)}")

                # 更新完整的历史数据（包含DatetimeIndex）
                self.model.last_train_data = data.copy()

                # 更新滑动窗口的最后值
                max_window = max(self.model.lag_features, 50)
                self.model.last_train_values = data.values[-max_window:].copy()

                logger.debug(f"已更新预测起点: 完整历史={len(data)}, 窗口={max_window}")

        else:
            logger.warning(f"模型类型 {model_type} 的预测起点更新尚未实现")

    def _log_config(self):
        """记录配置到 MLflow"""
        config_dict = self.config.to_dict()

        # 递归展平嵌套配置（支持任意深度）
        flat_config = MLFlowUtils.flatten_dict(config_dict)

        # 记录模型参数
        model_params = self.model.get_params()
        for key, value in model_params.items():
            flat_config[f"model_{key}"] = value

        MLFlowUtils.log_params_batch(flat_config)
        logger.debug(f"配置已记录到 MLflow，共 {len(flat_config)} 个参数")

    def _save_model_to_mlflow(self) -> str:
        """保存模型到 MLflow（自动支持所有实现了 save_mlflow 的模型）

        Returns:
            模型 URI
        """
        logger.info("保存模型到 MLflow...")

        model_type = self.config.model_type

        # 检查模型是否有 save_mlflow 方法（鸭子类型）
        if hasattr(self.model, "save_mlflow") and callable(
            getattr(self.model, "save_mlflow")
        ):
            try:
                self.model.save_mlflow(artifact_path="model")
                logger.info(f"{model_type} 模型已保存")
            except Exception as e:
                logger.error(f"模型保存失败: {e}")
                raise
        else:
            logger.warning(f"模型类型 {model_type} 没有实现 save_mlflow 方法")

        model_uri = f"runs:/{mlflow.active_run().info.run_id}/model"
        return model_uri

    def _register_model(self, model_uri: Optional[str]):
        """注册模型到 MLflow Model Registry

        Args:
            model_uri: 模型 URI
        """
        if not model_uri:
            logger.warning("模型 URI 为空，跳过注册")
            return

        model_name = self.config.model_name

        try:
            logger.info(f"注册模型到 Model Registry: {model_name}")
            model_version = mlflow.register_model(model_uri, model_name)
            logger.info(f"模型注册成功: {model_name}, 版本: {model_version.version}")
        except Exception as e:
            logger.warning(f"模型注册失败: {e}")

    def predict(self, steps: int) -> np.ndarray:
        """使用训练好的模型进行预测

        Args:
            steps: 预测步数

        Returns:
            预测结果数组

        Raises:
            RuntimeError: 模型未训练
        """
        if self.model is None:
            raise RuntimeError("模型未训练，请先调用 train() 方法")

        return self.model.predict(steps)

    def __repr__(self) -> str:
        model_info = f"model={self.model}" if self.model else "model=None"
        return f"UniversalTrainer(model_type={self.config.model_type}, {model_info})"
