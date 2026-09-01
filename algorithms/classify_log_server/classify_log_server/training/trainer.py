"""日志聚类模型通用训练器"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
import datetime

from loguru import logger
import mlflow

from .config.loader import TrainingConfig
from .data_loader import LogDataLoader
from .evaluation_contract import EVALUATION_CONTRACT_VERSION
from .mlflow_utils import MLFlowUtils
from .models.base import ModelRegistry
from .models import SpellModel  # 导入具体模型以触发注册
from .preprocessing.log_preprocessor import LogPreprocessor, LogParser
from .preprocessing.feature_engineering import LogFeatureEngineer, prepare_log_dataframe


class UniversalTrainer:
    """日志聚类模型通用训练器

    处理完整的训练流程：
    1. 加载配置
    2. 加载和预处理数据
    3. 训练模型（可选超参数优化）
    4. 评估模型
    5. 保存模型并记录到 MLflow
    """

    def __init__(self, config: TrainingConfig):
        """初始化训练器

        Args:
            config: 训练配置
        """
        self.config = config
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化数据加载器
        self.data_loader = LogDataLoader(encoding="utf-8")

        # 预处理组件（延迟初始化）
        self.log_parser = None
        self.preprocessor = None
        self.feature_engineer = None
        self.model = None

        logger.info(f"训练器初始化 - 模型类型: {config.model_type}")

    def train(self, dataset_path: str) -> Dict[str, Any]:
        """执行完整训练流程

        Args:
            dataset_path: 数据集路径（目录或单个TXT文件）
                         - 目录模式：包含 train.txt/val.txt/test.txt
                         - 文件模式：单个TXT文件

        Returns:
            训练结果字典（指标、模型路径等）
        """
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.model_type}")
        logger.info("=" * 60)

        # 1. 设置 MLflow
        self._setup_mlflow()

        # 2. 加载数据
        train_logs, val_logs, test_logs = self._load_data(dataset_path)

        # 3. 数据预处理
        train_data, val_data, test_data = self._preprocess_data(
            train_logs, val_logs, test_logs
        )

        # 4. 创建模型实例
        self.model = self._create_model()

        # 5. 开始 MLflow run
        with mlflow.start_run(run_name=self.config.mlflow_run_name) as run:
            try:
                # 记录配置
                self._log_config()

                # 记录数据信息
                self._log_data_info(train_logs, val_logs, test_logs)

                # 6. 超参数优化（如果配置了）
                best_params = None
                if val_data:
                    best_params = self._optimize_hyperparams(train_data, val_data)
                    if best_params:
                        MLFlowUtils.log_params_batch(
                            {f"best_{k}": v for k, v in best_params.items()}
                        )
                        logger.info(f"最优参数: {best_params}")

                        # 用最优参数重新创建模型
                        logger.info("使用最优参数重新创建模型...")
                        self.model = ModelRegistry.create_model(
                            self.config.model_type, **best_params
                        )

                # 7. 训练模型
                self._train_model(train_data, val_data)

                # 8. 评估训练集拟合度（样本内评估）
                if val_data:
                    # 合并train+val评估最终训练数据
                    final_train_data = train_data + val_data
                    logger.info("评估最终训练数据拟合度（train+val样本内评估）...")
                    final_train_metrics = self.model.evaluate(final_train_data)
                    # 使用 MLFlowUtils 批量记录（自动过滤）
                    MLFlowUtils.log_metrics_batch(
                        final_train_metrics, prefix="final_train_"
                    )
                    MLFlowUtils.log_params_batch(
                        {
                            "final_train_samples": len(final_train_data),
                            "final_train_merge_val": True,
                        }
                    )
                    # 只输出数值统计指标到日志
                    summary = {
                        k: v
                        for k, v in final_train_metrics.items()
                        if not k.startswith("_") and isinstance(v, (int, float))
                    }
                    logger.info(f"最终训练数据拟合度评估完成: {summary}")
                else:
                    # 无验证集，只评估训练集
                    logger.info("评估训练集拟合度（样本内评估）...")
                    train_metrics = self.model.evaluate(train_data)
                    # 使用 MLFlowUtils 批量记录
                    MLFlowUtils.log_metrics_batch(train_metrics, prefix="train_")
                    # 只输出数值统计指标到日志
                    summary = {
                        k: v
                        for k, v in train_metrics.items()
                        if not k.startswith("_") and isinstance(v, (int, float))
                    }
                    logger.info(f"训练集拟合度评估完成: {summary}")

                # 9. 评估测试集
                test_metrics = {}
                if test_data:
                    logger.info("评估测试集...")
                    test_metrics = self.model.evaluate(test_data)
                    # 使用 MLFlowUtils 批量记录
                    MLFlowUtils.log_metrics_batch(test_metrics, prefix="test_")
                    # 只输出数值统计指标到日志
                    test_summary = {
                        k: v
                        for k, v in test_metrics.items()
                        if not k.startswith("_") and isinstance(v, (int, float))
                    }
                    logger.info(f"测试集评估完成: {test_summary}")

                    # 生成覆盖率对比可视化（训练集 vs 测试集）
                    try:
                        train_predictions = self.model.predict(train_data)
                        test_predictions = self.model.predict(test_data)
                        MLFlowUtils.plot_coverage_comparison(
                            train_cluster_ids=train_predictions,
                            test_cluster_ids=test_predictions,
                            noise_label=-1,
                        )
                        logger.info("✓ 覆盖率对比可视化已生成")
                    except Exception as e:
                        logger.warning(f"生成覆盖率对比可视化失败: {e}")

                    # 生成指标对比可视化
                    try:
                        # 使用final_train_metrics或train_metrics
                        train_cmp_metrics = (
                            final_train_metrics if val_data else train_metrics
                        )
                        MLFlowUtils.plot_clustering_metrics_comparison(
                            train_metrics=train_cmp_metrics, test_metrics=test_metrics
                        )
                    except Exception as e:
                        logger.warning(f"生成指标对比图失败: {e}")
                else:
                    logger.info("⚠ 未找到 test.txt，使用训练集指标作为测试集评估")
                    if val_data:
                        test_metrics = {
                            k.replace("final_train_", "test_"): v
                            for k, v in final_train_metrics.items()
                        }
                    else:
                        test_metrics = {
                            k.replace("train_", "test_"): v
                            for k, v in train_metrics.items()
                        }

                # 10. 保存模型到 MLflow
                model_uri = self._save_model_to_mlflow()

                # 11. 注册模型到 MLflow Model Registry（如果配置启用）
                self._register_model(model_uri)

                # 生成结果
                result = {
                    "model": self.model,
                    "model_type": self.config.model_type,
                    "test_metrics": test_metrics,
                    "num_train_logs": len(train_logs),
                    "num_val_logs": len(val_logs) if val_logs else 0,
                    "num_test_logs": len(test_logs) if test_logs else 0,
                    "num_templates": self.model.get_num_templates(),
                    "run_id": run.info.run_id,
                    "best_params": best_params,
                    "evaluation_contract_version": EVALUATION_CONTRACT_VERSION,
                }

                # 过滤测试集指标，只输出数值统计
                test_summary = {
                    k: v
                    for k, v in test_metrics.items()
                    if not k.startswith("_") and isinstance(v, (int, float))
                }

                logger.info("=" * 60)
                logger.info("训练完成")
                logger.info(f"MLflow Run ID: {run.info.run_id}")
                logger.info(f"测试集指标: {test_summary}")
                logger.info("=" * 60)

                return result

            except Exception as e:
                logger.error(f"训练过程出错: {e}")
                MLFlowUtils.log_params_batch({"training_failed": True})
                raise

    def _load_data(
        self, dataset_path: str
    ) -> Tuple[List[str], Optional[List[str]], Optional[List[str]]]:
        """加载训练、验证和测试数据

        支持两种模式：
        1. 目录模式：dataset_path 为目录
           - 必须包含 train.txt
           - 可选 val.txt 和 test.txt
        2. 文件模式：dataset_path 为单个TXT文件
           - 作为训练数据

        Args:
            dataset_path: 数据集路径（目录或文件）

        Returns:
            元组 (train_logs, val_logs, test_logs)
        """
        import os
        from pathlib import Path

        logger.info("加载数据...")

        dataset_path = Path(dataset_path)

        if dataset_path.is_dir():
            # 目录模式
            logger.info(f"📁 检测到目录模式: {dataset_path}")

            train_file = dataset_path / "train_data.txt"
            if not train_file.exists():
                raise FileNotFoundError(
                    f"目录模式下未找到训练文件: {train_file}\n"
                    f"目录中必须包含 train_data.txt"
                )

            train_logs = self.data_loader.load_txt(str(train_file))
            logger.info(f"✓ 训练集: {len(train_logs)} 条日志 (train_data.txt)")

            # 可选的验证集
            val_logs = None
            val_file = dataset_path / "val_data.txt"
            if val_file.exists():
                val_logs = self.data_loader.load_txt(str(val_file))
                logger.info(f"✓ 验证集: {len(val_logs)} 条日志 (val_data.txt)")
            else:
                logger.info("⚠ 未找到 val_data.txt，将跳过验证")

            # 可选的测试集
            test_logs = None
            test_file = dataset_path / "test_data.txt"
            if test_file.exists():
                test_logs = self.data_loader.load_txt(str(test_file))
                logger.info(f"✓ 测试集: {len(test_logs)} 条日志 (test_data.txt)")
            else:
                logger.info("⚠ 未找到 test_data.txt，将使用训练集进行评估")

            return train_logs, val_logs, test_logs

        elif dataset_path.is_file():
            # 文件模式 - 单个文件作为训练数据
            logger.info(f"📄 检测到文件模式: {dataset_path}")
            train_logs = self.data_loader.load_txt(str(dataset_path))
            logger.info(f"✓ 加载 {len(train_logs)} 条日志从单个文件")

            return train_logs, None, None

        else:
            raise FileNotFoundError(f"数据集路径未找到: {dataset_path}")

    def _preprocess_data(
        self,
        train_logs: List[str],
        val_logs: Optional[List[str]],
        test_logs: Optional[List[str]],
    ) -> Tuple[List[str], Optional[List[str]], Optional[List[str]]]:
        """数据预处理（解析 + 清洗）

        一次性初始化所有组件并处理所有数据集。

        Args:
            train_logs: 训练集原始日志
            val_logs: 验证集原始日志（可选）
            test_logs: 测试集原始日志（可选）

        Returns:
            (train_logs_processed, val_logs_processed, test_logs_processed)
        """
        logger.info("数据预处理（解析 + 清洗）...")

        # 1. 初始化组件（只初始化一次）
        self.log_parser = LogParser(log_format="<Content>")
        preprocessing_config = self.config.config.get("preprocessing", {})
        self.preprocessor = LogPreprocessor(preprocessing_config)

        logger.info(f"预处理配置: {preprocessing_config}")

        # 2. 处理训练集
        train_logs_processed = self._preprocess_single(train_logs)
        logger.info(f"训练集预处理完成: {len(train_logs_processed)} 条日志")

        # 3. 处理验证集
        val_logs_processed = None
        if val_logs:
            val_logs_processed = self._preprocess_single(val_logs)
            logger.info(f"验证集预处理完成: {len(val_logs_processed)} 条日志")

        # 4. 处理测试集
        test_logs_processed = None
        if test_logs:
            test_logs_processed = self._preprocess_single(test_logs)
            logger.info(f"测试集预处理完成: {len(test_logs_processed)} 条日志")

        return train_logs_processed, val_logs_processed, test_logs_processed

    def _preprocess_single(self, logs: List[str]) -> List[str]:
        """处理单个数据集

        Args:
            logs: 原始日志列表

        Returns:
            处理后的日志列表
        """
        # 解析日志提取内容
        contents = self.log_parser.extract_content(logs)

        # 应用预处理
        processed = self.preprocessor.preprocess(contents)

        return processed

    def _setup_mlflow(self):
        """设置 MLflow 实验"""
        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name

        # 使用 MLFlowUtils 统一设置
        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)

    def _log_config(self):
        """记录配置到 MLflow"""
        config_dict = self.config.to_dict()

        # 递归展平嵌套配置（支持任意深度）
        flat_config = MLFlowUtils.flatten_dict(config_dict)
        flat_config["evaluation_contract_version"] = EVALUATION_CONTRACT_VERSION

        MLFlowUtils.log_params_batch(flat_config)
        logger.debug(f"配置已记录到 MLflow，共 {len(flat_config)} 个参数")

    def _create_model(self):
        """创建模型实例"""
        logger.info(f"创建模型: {self.config.model_type}")

        # 从search_space中获取tau（第一个值）
        search_space = self.config.get("hyperparams", "search_space", default={})
        tau_values = search_space.get("tau", [0.5])
        tau = tau_values[0] if isinstance(tau_values, list) else tau_values

        # 使用 **kwargs 方式创建模型
        model = ModelRegistry.create_model(self.config.model_type, tau=tau)
        logger.info(f"模型已创建: {model.__class__.__name__} (tau={tau})")

        return model

    def _optimize_hyperparams(
        self, train_data: List[str], val_data: List[str]
    ) -> Dict[str, Any]:
        """统一的超参数优化入口

        Args:
            train_data: 训练数据
            val_data: 验证数据

        Returns:
            最优超参数字典，如果不支持或配置为0则返回 {}
        """
        logger.info("检查超参数优化配置...")

        # 1. 检查配置
        max_evals = self.config.get("hyperparams", "max_evals", default=0)

        if max_evals == 0:
            logger.info("max_evals=0，跳过超参数优化")
            return {}

        # 2. 检查模型是否支持超参数优化
        if not hasattr(self.model, "optimize_hyperparams"):
            logger.warning(f"{self.config.model_type} 模型不支持超参数优化，跳过")
            return {}

        # 3. 执行优化
        logger.info(f"开始超参数优化: max_evals={max_evals}")
        try:
            best_params = self.model.optimize_hyperparams(
                train_data=train_data, val_data=val_data, config=self.config
            )
            logger.info(f"超参数优化完成: {best_params}")
            return best_params
        except Exception as e:
            logger.error(f"超参数优化失败: {e}", exc_info=True)
            return {}

    def _train_model(self, train_data: List[str], val_data: Optional[List[str]]):
        """训练模型

        Args:
            train_data: 训练数据
            val_data: 验证数据（可选）
        """
        logger.info("训练模型...")

        # 将预处理器附加到模型（用于推理时使用）
        if self.preprocessor:
            self.model.preprocessor = self.preprocessor
            logger.info("✓ 预处理器已附加到模型")
        else:
            logger.warning("⚠ 未找到预处理器，推理时可能需要手动预处理")

        # 如果有验证集，合并后训练
        if val_data:
            final_train_data = train_data + val_data
            logger.info(f"合并训练集和验证集: {len(final_train_data)} 条日志")
            self.model.fit(final_train_data, verbose=True, log_to_mlflow=True)
        else:
            self.model.fit(train_data, verbose=True, log_to_mlflow=True)

        logger.info("模型训练完成")

    def _save_model_to_mlflow(self) -> str:
        """保存模型到 MLflow

        Returns:
            模型 URI
        """
        logger.info("保存模型到 MLflow...")

        model_type = self.config.model_type

        # 检查模型是否有 save_mlflow 方法
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
            logger.warning(f"{model_type} 模型不支持 save_mlflow 方法")

        # 返回模型 URI
        run = mlflow.active_run()
        model_uri = f"runs:/{run.info.run_id}/model"

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

    def _generate_run_name(self):
        """生成基于模型类型和时间戳的 run 名称。"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.config.model_type}_{timestamp}"

    def _log_data_info(
        self,
        train_logs: List[str],
        val_logs: Optional[List[str]],
        test_logs: Optional[List[str]],
    ):
        """记录数据集信息到 MLflow

        Args:
            train_logs: 训练集日志
            val_logs: 验证集日志（可选）
            test_logs: 测试集日志（可选）
        """
        # 数据基本信息
        params = {
            "train_logs_count": len(train_logs),
        }

        if val_logs:
            params["val_logs_count"] = len(val_logs)

        if test_logs:
            params["test_logs_count"] = len(test_logs)

        # 批量记录参数
        MLFlowUtils.log_params_batch(params)
        logger.debug(f"数据信息已记录到 MLflow: {params}")
