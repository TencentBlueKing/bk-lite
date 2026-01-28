"""通用目标检测训练器."""

from typing import Dict, Any, Optional
import mlflow
from loguru import logger
import torch

from .config.loader import TrainingConfig
from .models.base import ModelRegistry
from .preprocessing import ImagePreprocessor, ImageFeatureEngineer
from .data_loader import load_yolo_dataset
from .mlflow_utils import MLFlowUtils


class UniversalTrainer:
    """通用目标检测训练器.

    实现标准的10步训练流程：
    1. MLflow实验设置
    2. 数据加载
    3. 数据预处理
    4. 模型实例化
    5. 开始MLflow run
    6. 记录配置参数
    7. 超参数优化（可选）
    8. 模型训练
    9. 模型评估
    10. 模型保存和注册
    """

    def __init__(self, config: TrainingConfig):
        """
        初始化训练器.

        Args:
            config: 训练配置对象
        """
        self.config = config
        self.model = None
        self.preprocessor = None
        self.feature_engineer = None
        self.dataset_yaml = None

        # 解析设备配置
        self.device = self._resolve_device()

        logger.info(f"训练器初始化 - 模型类型: {config.model_type}")
        logger.info(f"训练设备: {self.device}")

    def train(self, dataset_yaml_path: str) -> Dict[str, Any]:
        """
        执行完整训练流程.

        Args:
            dataset_yaml_path: YOLO格式数据集配置文件路径（data.yaml 或 dataset.yaml）

        Returns:
            训练结果字典
        """
        logger.info("=" * 60)
        logger.info(f"开始训练 - 模型: {self.config.model_type}")
        logger.info("=" * 60)

        # 1. 设置MLflow
        self._setup_mlflow()

        # 2. 加载数据
        self.dataset_yaml = self._load_data(dataset_yaml_path)

        # 3. 数据预处理
        self._preprocess_data(dataset_yaml_path)

        # 4. 创建模型实例
        self.model = self._create_model()

        # 5. 开始MLflow run
        with mlflow.start_run(run_name=self.config.mlflow_run_name) as run:
            try:
                # 6. 记录配置
                self._log_config()

                # 7. 超参数优化（可选）
                best_params = None
                max_evals = self.config.get("hyperparams", "max_evals", default=0)
                if max_evals > 0:
                    logger.info(f"开始超参数优化，最大评估次数: {max_evals}")
                    best_params = self._optimize_hyperparams()
                    if best_params:
                        MLFlowUtils.log_params_batch(best_params)
                        logger.info(f"最优超参数: {best_params}")

                # 8. 训练模型
                self._train_model()

                # 9. 评估模型
                test_metrics = self._evaluate_model_on_test()

                # 10. 保存模型到MLflow并注册
                model_uri = self._save_model_to_mlflow()
                self._register_model(model_uri)

                logger.info("=" * 60)
                logger.info("训练完成！")
                logger.info("=" * 60)

                return {
                    "model": self.model,
                    "test_metrics": test_metrics,
                    "run_id": run.info.run_id,
                    "best_params": best_params,
                }

            except Exception as e:
                logger.error(f"训练过程出错: {e}", exc_info=True)
                raise

    def _resolve_device(self) -> str:
        """
        解析设备配置.

        Returns:
            YOLO device参数（如'0', 'cpu', '0,1,2,3'）
        """
        device_mode = self.config.get_device_config()

        if device_mode == "cpu":
            return self._resolve_cpu()
        elif device_mode == "gpu":
            return self._resolve_gpu()
        elif device_mode == "gpus":
            return self._resolve_gpus()
        elif device_mode == "auto":
            return self._resolve_auto()
        else:
            raise ValueError(f"不支持的device模式: {device_mode}")

    def _resolve_cpu(self) -> str:
        """强制CPU模式."""
        if torch.cuda.is_available():
            logger.warning("⚠️  配置指定使用CPU，但检测到可用GPU")
        logger.info("💻 使用CPU训练")
        return "cpu"

    def _resolve_gpu(self) -> str:
        """单GPU模式."""
        if not torch.cuda.is_available():
            raise RuntimeError(
                "配置指定使用GPU，但未检测到可用GPU。\n"
                "请检查：\n"
                "1. 是否安装了GPU版本的PyTorch\n"
                "2. CUDA是否正确安装\n"
                "3. 或将配置改为 device='cpu'"
            )

        gpu_name = torch.cuda.get_device_name(0)
        logger.info(f"🚀 使用单GPU训练: {gpu_name} (GPU 0)")
        return "0"

    def _resolve_gpus(self) -> str:
        """多GPU分布式训练模式."""
        if not torch.cuda.is_available():
            raise RuntimeError("配置指定多GPU训练，但未检测到可用GPU")

        available_gpus = torch.cuda.device_count()

        if available_gpus < 2:
            logger.warning(
                f"⚠️  配置为多GPU模式，但只有{available_gpus}块GPU\n"
                f"   自动降级为单GPU模式"
            )
            return "0"

        # 使用所有GPU
        gpu_ids = list(range(available_gpus))
        gpu_names = [torch.cuda.get_device_name(i) for i in gpu_ids]

        logger.info(
            f"🚀🚀 使用多GPU分布式训练 ({len(gpu_ids)}块GPU):\n"
            + "\n".join([f"   GPU {i}: {name}" for i, name in zip(gpu_ids, gpu_names)])
        )

        # YOLO的多GPU格式：'0,1,2,3'
        yolo_device = ",".join(map(str, gpu_ids))
        return yolo_device

    def _resolve_auto(self) -> str:
        """自动检测模式."""
        if not torch.cuda.is_available():
            logger.warning(
                "⚠️  未检测到GPU，使用CPU训练\n   提示：CPU训练速度很慢，强烈建议使用GPU"
            )
            return "cpu"

        gpu_count = torch.cuda.device_count()
        gpu_names = [torch.cuda.get_device_name(i) for i in range(gpu_count)]

        if gpu_count == 1:
            logger.info(f"🚀 自动检测：使用单GPU训练\n   GPU 0: {gpu_names[0]}")
            return "0"
        else:
            logger.info(
                f"🚀 自动检测：发现{gpu_count}块GPU，使用单GPU模式（GPU 0）\n"
                + "\n".join([f"   GPU {i}: {name}" for i, name in enumerate(gpu_names)])
                + f"\n\n💡 提示：如需多GPU训练，请设置配置：\n"
                f'   "device": "gpus"'
            )
            return "0"

    def _setup_mlflow(self):
        """设置MLflow实验."""
        tracking_uri = self.config.mlflow_tracking_uri
        experiment_name = self.config.mlflow_experiment_name

        MLFlowUtils.setup_experiment(tracking_uri, experiment_name)

    def _load_data(self, dataset_yaml_path: str) -> str:
        """
        加载YOLO格式数据集.

        Returns:
            数据集配置文件的绝对路径
        """
        logger.info(f"加载数据集: {dataset_yaml_path}")
        return load_yolo_dataset(dataset_yaml_path)

    def _preprocess_data(self, dataset_yaml_path: str):
        """
        数据预处理.
        """
        logger.info("数据预处理...")

        # 初始化预处理器
        self.preprocessor = ImagePreprocessor(self.config.preprocessing_config)

        # 验证数据集
        validation_result = self.preprocessor.validate_dataset(dataset_yaml_path)
        if not validation_result["valid"]:
            logger.error(f"数据集验证失败: {validation_result['errors']}")
            raise ValueError("数据集验证失败")

        # 初始化特征工程器
        self.feature_engineer = ImageFeatureEngineer(
            self.config.feature_engineering_config
        )

        logger.info("数据预处理完成")

    def _create_model(self):
        """创建模型实例."""
        model_type = self.config.model_type
        hyperparams = self.config.hyperparams_config.copy()

        # 将设备信息传递给模型（供超参数优化使用）
        hyperparams["_device"] = self.device

        logger.info(f"创建模型: {model_type}")
        model = ModelRegistry.create(model_type, **hyperparams)

        return model

    def _log_config(self):
        """记录配置到MLflow."""
        logger.info("记录配置到MLflow...")

        # 使用统一的to_dict()方法导出配置
        config_dict = self.config.to_dict()

        # 展开嵌套的配置
        flat_config = {}
        for key, value in config_dict.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat_config[f"{key}.{sub_key}"] = sub_value
            else:
                flat_config[key] = value

        # 记录设备信息
        flat_config["device"] = self.device

        MLFlowUtils.log_params_batch(flat_config)
        logger.debug(f"配置已记录到 MLflow")

    def _optimize_hyperparams(self) -> Optional[Dict[str, Any]]:
        """超参数优化."""
        max_evals = self.config.get("hyperparams", "max_evals", default=0)
        if max_evals == 0:
            return None

        try:
            return self.model.optimize_hyperparams(
                self.dataset_yaml, self.dataset_yaml, max_evals
            )
        except Exception as e:
            logger.error(f"超参数优化失败: {e}")
            return None

    def _train_model(self):
        """训练模型."""
        logger.info("开始训练模型...")

        # 将feature_engineering配置传递给模型（用于YOLO数据增强）
        feature_config = self.config.feature_engineering_config
        if feature_config:
            augment_enabled = feature_config.get("enabled", True)
            if not augment_enabled:
                self.model.hyperparams["augment"] = False
                logger.info("⚠️  数据增强已禁用")
            else:
                # 传递检测专用增强参数给YOLO
                augment_params = {}

                # 几何变换参数
                for key in [
                    "degrees",
                    "translate",
                    "scale",
                    "shear",
                    "perspective",
                    "fliplr",
                    "flipud",
                ]:
                    if key in feature_config:
                        augment_params[key] = feature_config[key]

                # 颜色增强参数
                for key in ["hsv_h", "hsv_s", "hsv_v"]:
                    if key in feature_config:
                        augment_params[key] = feature_config[key]

                # 检测专用高级增强
                for key in ["mosaic", "mixup", "copy_paste"]:
                    if key in feature_config:
                        augment_params[key] = feature_config[key]

                if augment_params:
                    self.model.hyperparams.update(augment_params)
                    logger.info(f"✓ 自定义数据增强参数: {augment_params}")

        self.model.fit(self.dataset_yaml, device=self.device)
        logger.info("模型训练完成")

    def _evaluate_model_on_test(self) -> Dict[str, float]:
        """在测试集上评估模型."""
        logger.info("在测试集上评估模型...")
        test_metrics = self.model.evaluate(
            self.dataset_yaml, prefix="test", log_artifacts=True
        )

        # 记录指标到MLflow
        MLFlowUtils.log_metrics_batch(test_metrics, prefix="")

        # 输出到日志（只输出数值指标）
        summary = {
            k: v
            for k, v in test_metrics.items()
            if not k.startswith("_") and isinstance(v, (int, float))
        }
        logger.info(f"测试集评估完成: {summary}")

        return test_metrics

    def _save_model_to_mlflow(self) -> str:
        """保存模型到MLflow."""
        logger.info("保存模型到MLflow...")

        try:
            self.model.save_mlflow(artifact_path="model")
            logger.info("模型已保存")
        except Exception as e:
            logger.error(f"模型保存失败: {e}")
            raise

        model_uri = f"runs:/{mlflow.active_run().info.run_id}/model"
        return model_uri

    def _register_model(self, model_uri: str):
        """注册模型到MLflow Model Registry."""
        if not model_uri:
            logger.warning("模型URI为空，跳过注册")
            return

        model_name = self.config.model_name

        try:
            logger.info(f"注册模型到Model Registry: {model_name}")
            model_version = mlflow.register_model(model_uri, model_name)
            logger.info(f"✓ 模型注册成功: {model_name}, 版本: {model_version.version}")
        except Exception as e:
            logger.warning(f"模型注册失败: {e}")
