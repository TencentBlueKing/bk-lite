"""YOLO图片分类模型封装."""

from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import mlflow
from loguru import logger
from ultralytics import YOLO, settings
import uuid
import time
import logging

from classify_image_classification_server import PROJECT_ROOT
from .base import BaseImageClassificationModel, ModelRegistry

# 禁用YOLO的MLflow自动集成，避免与自定义MLflow管理冲突
settings.update({"mlflow": False})

# 禁用YOLO的详细日志输出
logging.getLogger("ultralytics").setLevel(logging.WARNING)

logger.info("已禁用YOLO的MLflow自动集成和详细日志")


@ModelRegistry.register("YOLOClassification")
class YOLOClassificationModel(BaseImageClassificationModel):
    """YOLO图片分类模型.

    封装ultralytics YOLO，实现统一的训练和推理接口。
    """

    def __init__(self, model_name: str = "yolo11n-cls.pt", **hyperparams):
        """
        初始化YOLO模型.

        Args:
            model_name: YOLO模型名称（如yolo11n-cls.pt, yolo11s-cls.pt等）或绝对路径
            **hyperparams: 其他超参数
        """
        # 解析模型路径（名称 → 本地路径）
        self.model_name = self._resolve_model_path(model_name)
        self.hyperparams = hyperparams
        self.yolo = None
        self.class_names = None
        self._results = None

        logger.info(f"YOLOClassificationModel初始化: {self.model_name}")

    @staticmethod
    def _resolve_model_path(model_name: str) -> str:
        """解析模型名称为本地路径.

        优先使用本地模型文件，如果不存在则回退到Ultralytics在线下载模式。

        Args:
            model_name: 模型名称（如 "yolo11n-cls.pt"）或绝对路径

        Returns:
            解析后的模型路径（本地路径或原始名称）

        Examples:
            >>> _resolve_model_path("yolo11n-cls.pt")
            "/apps/yolo_models/yolo11n-cls.pt"  # 如果文件存在

            >>> _resolve_model_path("/custom/path/model.pt")
            "/custom/path/model.pt"  # 绝对路径直接返回

            >>> _resolve_model_path("yolo11n-cls.pt")
            "yolo11n-cls.pt"  # 本地文件不存在时回退
        """
        from pathlib import Path
        from classify_image_classification_server import PROJECT_ROOT

        # 1. 如果是绝对路径，直接返回
        if Path(model_name).is_absolute():
            logger.info(f"使用自定义模型路径: {model_name}")
            return model_name

        # 2. 构建本地路径
        local_model_path = PROJECT_ROOT / "yolo_models" / model_name

        # 3. 检查文件是否存在
        if local_model_path.exists():
            logger.info(f"✓ 使用本地模型: {local_model_path}")
            return str(local_model_path)

        # 4. 回退到原始名称（触发Ultralytics在线下载）
        logger.warning(
            f"⚠️  本地模型文件不存在: {local_model_path}\n"
            f"   将使用 Ultralytics 在线下载模式: {model_name}\n"
            f"   提示：镜像仅内置 Dockerfile 声明的官方权重；"
            f"自定义权重请在运行时通过绝对路径提供"
        )
        return model_name

    def _get_param_value(self, param_name: str, default_value):
        """
        智能获取参数值：优先使用搜索空间中的默认值，其次使用固定值，最后使用代码默认值.

        如果参数在 search_space 中定义，则使用搜索空间的第一个值作为默认值，
        忽略 hyperparams 中的固定值，避免配置混淆。

        Args:
            param_name: 参数名称
            default_value: 代码中的默认值（最终回退值）

        Returns:
            参数值
        """
        search_space = self.hyperparams.get("search_space", {})

        # 如果参数在搜索空间中定义，使用搜索空间的第一个值
        if param_name in search_space:
            space_config = search_space[param_name]
            if isinstance(space_config, list) and len(space_config) > 0:
                # 搜索空间是列表，取第一个值作为默认值
                return space_config[0]
            elif isinstance(space_config, dict):
                # 搜索空间是字典配置
                if space_config.get("type") == "choice":
                    options = space_config.get("options", [])
                    if options:
                        return options[0]
                # 其他类型（uniform, loguniform等）使用 low 作为默认值
                return space_config.get("low", default_value)

        # 否则使用 hyperparams 中的固定值
        return self.hyperparams.get(param_name, default_value)

    def fit(
        self,
        train_data: Tuple[str, List[str]],
        val_data: Optional[Tuple[str, List[str]]] = None,
        device: str = "auto",
        log_artifacts: bool = True,
        **kwargs,
    ) -> "YOLOClassificationModel":
        """
        训练YOLO模型.

        Args:
            train_data: (train_path, class_names)
            val_data: (val_path, class_names) 可选
            device: 设备配置
            log_artifacts: 是否上传训练产生的artifacts到MLflow，默认True
            **kwargs: 额外训练参数

        Returns:
            self
        """
        train_path, class_names = train_data
        self.class_names = class_names

        logger.info(f"开始训练YOLO模型，设备: {device}")
        logger.info(f"训练集: {train_path}, 类别数: {len(class_names)}")

        # 初始化YOLO模型
        self.yolo = YOLO(self.model_name)

        # YOLO需要数据集根目录，不是train子目录
        # 从train_path提取根目录: /path/to/dataset/train -> /path/to/dataset
        from pathlib import Path

        dataset_root = str(Path(train_path).parent)
        logger.info(f"数据集根目录: {dataset_root}")

        # 构建训练参数
        train_kwargs = {
            "data": dataset_root,
            "epochs": self.hyperparams.get("epochs", 100),
            "imgsz": self._get_param_value("imgsz", 224),
            "batch": self._get_param_value("batch", 16),
            "lr0": self._get_param_value("lr0", 0.01),
            "lrf": self.hyperparams.get("lrf", 0.01),
            "momentum": self.hyperparams.get("momentum", 0.937),
            "weight_decay": self.hyperparams.get("weight_decay", 0.0005),
            "warmup_epochs": self.hyperparams.get("warmup_epochs", 3.0),
            "optimizer": self.hyperparams.get("optimizer", "AdamW"),
            "amp": self.hyperparams.get("amp", True),
            "patience": self.hyperparams.get("patience", 50),
            "device": device,
            "project": PROJECT_ROOT / ".yolo_runs" / "training",
            "name": f"train_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "save": True,
            "plots": True,
            "verbose": False,
        }

        if self.hyperparams.get("augment") is False:
            train_kwargs["augment"] = False
        else:
            for aug_param in [
                "degrees",
                "translate",
                "scale",
                "fliplr",
                "flipud",
                "hsv_h",
                "hsv_s",
                "hsv_v",
            ]:
                if aug_param in self.hyperparams:
                    train_kwargs[aug_param] = self.hyperparams[aug_param]

        if val_data:
            val_path, _ = val_data
            train_kwargs["val"] = True
            logger.info(f"使用验证集: {val_path}")

        if device != "cpu" and self.hyperparams.get("amp", True):
            train_kwargs["amp"] = True
            logger.info("⚡ 启用混合精度训练（AMP）")

        # 禁用YOLO的详细输出(模型架构等)
        train_kwargs["verbose"] = False

        # 执行训练
        logger.info(
            f"🚀 开始训练 - epochs={train_kwargs['epochs']}, batch={train_kwargs['batch']}, imgsz={train_kwargs['imgsz']}"
        )
        logger.info(f"📁 输出目录: {train_kwargs['project']}/{train_kwargs['name']}")

        train_start_time = time.time()
        results = self.yolo.train(**train_kwargs)
        train_duration = time.time() - train_start_time

        self._results = results

        # 记录训练loss变化信息
        loss_info = ""
        try:
            if hasattr(results, "results_dict") and results.results_dict:
                results_dict = results.results_dict
                if "train/loss" in results_dict:
                    final_loss = results_dict["train/loss"]
                    loss_info = f", 最终loss={final_loss:.4f}"
                    logger.info(f"📊 训练loss: {final_loss:.4f}")
        except Exception as e:
            logger.debug(f"无法获取loss信息: {e}")

        logger.info(f"✓ 训练完成 - 耗时: {train_duration / 60:.1f}分钟{loss_info}")

        # 手动上传YOLO训练产生的artifacts到MLflow（仅在最终训练时）
        if log_artifacts:
            self._log_yolo_artifacts_to_mlflow(train_kwargs)
        else:
            # 超参数优化时也要清理临时文件
            self._cleanup_yolo_output(train_kwargs)

        return self

    def predict(self, X: Any) -> List[int]:
        """
        批量预测.

        Args:
            X: 图片路径列表、PIL Image列表或numpy数组

        Returns:
            预测的类别索引列表
        """
        if self.yolo is None:
            raise RuntimeError("模型未训练，请先调用fit()方法")

        results = self.yolo.predict(
            X, imgsz=self.hyperparams.get("imgsz", 224), verbose=False
        )

        # 提取预测类别
        predictions = [r.probs.top1 for r in results]
        return predictions

    def evaluate(
        self,
        test_data: Tuple[str, List[str]],
        prefix: str = "test",
        log_artifacts: bool = False,
    ) -> Dict[str, float]:
        """
        评估模型性能.

        Args:
            test_data: (test_path, class_names)
            prefix: 指标前缀
            log_artifacts: 是否上传评估产生的artifacts到MLflow，默认False

        Returns:
            评估指标字典
        """
        if self.yolo is None:
            raise RuntimeError("模型未训练")

        test_path, class_names = test_data
        logger.info(f"在测试集上评估模型: {test_path}")

        from pathlib import Path

        dataset_root = str(Path(test_path).parent)
        logger.info(f"数据集根目录: {dataset_root}")

        eval_kwargs = {
            "data": dataset_root,
            "split": prefix,
            "verbose": False,
            "save": True,
            "plots": True,
            "project": PROJECT_ROOT / ".yolo_runs" / "validation",
            "name": f"eval_{prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        }

        metrics = self.yolo.val(**eval_kwargs)

        eval_results = {
            f"{prefix}_acc_top1": float(metrics.top1),
            f"{prefix}_acc_top5": float(metrics.top5),
        }

        if (
            hasattr(metrics, "confusion_matrix")
            and metrics.confusion_matrix is not None
        ):
            eval_results["_confusion_matrix"] = metrics.confusion_matrix.matrix

        logger.info(
            f"评估完成: top1_acc={eval_results[f'{prefix}_acc_top1']:.4f}, top5_acc={eval_results[f'{prefix}_acc_top5']:.4f}"
        )

        if log_artifacts:
            self._log_yolo_eval_artifacts_to_mlflow(eval_kwargs, prefix)
        else:
            self._cleanup_yolo_output(eval_kwargs)

        return eval_results

    def _log_yolo_artifacts_to_mlflow(self, train_kwargs: Dict[str, Any]):
        """
        手动上传YOLO训练产生的artifacts到MLflow.

        由于禁用了YOLO的MLflow自动集成，需要手动上传训练产生的文件。

        Args:
            train_kwargs: 训练参数，包含project和name
        """
        import shutil

        # 获取YOLO输出目录
        save_dir = Path(train_kwargs["project"]) / train_kwargs["name"]

        if not save_dir.exists():
            logger.warning(f"YOLO输出目录不存在: {save_dir}")
            return

        logger.info(f"开始上传YOLO训练artifacts到MLflow: {save_dir}")

        try:
            # 上传权重文件
            weights_dir = save_dir / "weights"
            if weights_dir.exists():
                logger.info("上传模型权重...")
                mlflow.log_artifacts(str(weights_dir), artifact_path="weights")

            # 上传训练结果文件
            files_to_upload = [
                "args.yaml",  # 训练参数
                "results.csv",  # 训练指标
                "results.png",  # 训练曲线
                "confusion_matrix.png",  # 混淆矩阵
                "confusion_matrix_normalized.png",  # 归一化混淆矩阵
            ]

            for filename in files_to_upload:
                file_path = save_dir / filename
                if file_path.exists():
                    logger.debug(f"上传文件: {filename}")
                    mlflow.log_artifact(str(file_path))

            # 上传训练过程的可视化图片（如果存在）
            for img_file in save_dir.glob("*.jpg"):
                logger.debug(f"上传图片: {img_file.name}")
                mlflow.log_artifact(str(img_file))

            for img_file in save_dir.glob("*.png"):
                if img_file.name not in files_to_upload:
                    logger.debug(f"上传图片: {img_file.name}")
                    mlflow.log_artifact(str(img_file))

            logger.info("✓ YOLO训练artifacts上传完成")

            # 清理输出目录
            self._cleanup_yolo_output(train_kwargs)

        except Exception as e:
            logger.error(f"上传artifacts到MLflow失败: {e}")
            # 不抛出异常，避免影响训练流程

    def _log_yolo_eval_artifacts_to_mlflow(
        self, eval_kwargs: Dict[str, Any], prefix: str = "test"
    ):
        """
        手动上传YOLO评估产生的artifacts到MLflow.

        Args:
            eval_kwargs: 评估参数，包含project和name
            prefix: 评估前缀（test/val等），用于组织artifacts目录结构
        """
        import shutil

        # 获取YOLO输出目录
        save_dir = Path(eval_kwargs["project"]) / eval_kwargs["name"]

        if not save_dir.exists():
            logger.warning(f"YOLO评估输出目录不存在: {save_dir}")
            return

        logger.info(f"开始上传YOLO评估artifacts到MLflow: {save_dir}")

        try:
            # 评估artifacts上传到子目录，避免与训练artifacts冲突
            artifact_path = f"{prefix}_evaluation"

            # 上传评估结果文件
            files_to_upload = [
                "confusion_matrix.png",  # 混淆矩阵
                "confusion_matrix_normalized.png",  # 归一化混淆矩阵
            ]

            for filename in files_to_upload:
                file_path = save_dir / filename
                if file_path.exists():
                    logger.debug(f"上传文件: {filename}")
                    mlflow.log_artifact(str(file_path), artifact_path=artifact_path)

            # 上传评估过程的可视化图片（batch预测样例）
            for img_file in save_dir.glob("*.jpg"):
                logger.debug(f"上传图片: {img_file.name}")
                mlflow.log_artifact(str(img_file), artifact_path=artifact_path)

            # 上传其他PNG图片（排除已上传的）
            for img_file in save_dir.glob("*.png"):
                if img_file.name not in files_to_upload:
                    logger.debug(f"上传图片: {img_file.name}")
                    mlflow.log_artifact(str(img_file), artifact_path=artifact_path)

            logger.info(f"✓ YOLO评估artifacts上传完成（目录: {artifact_path}）")

            # 清理输出目录
            self._cleanup_yolo_output(eval_kwargs)

        except Exception as e:
            logger.error(f"上传评估artifacts到MLflow失败: {e}")
            # 不抛出异常，避免影响评估流程

    def _cleanup_yolo_output(self, train_kwargs: Dict[str, Any]):
        """
        清理YOLO训练/评估输出目录.

        Args:
            train_kwargs: 训练/评估参数，包含project和name
        """
        import shutil

        save_dir = Path(train_kwargs["project"]) / train_kwargs["name"]

        if save_dir.exists():
            logger.debug(f"清理YOLO输出目录: {save_dir}")
            try:
                shutil.rmtree(save_dir, ignore_errors=True)
                logger.debug("✓ 输出目录已清理")
            except Exception as e:
                logger.warning(f"清理输出目录失败: {e}")

    def optimize_hyperparams(
        self,
        train_data: Tuple[str, List[str]],
        val_data: Tuple[str, List[str]],
        max_evals: int,
    ) -> Dict[str, Any]:
        """
        超参数优化（使用Hyperopt）.

        Args:
            train_data: 训练数据
            val_data: 验证数据
            max_evals: 最大评估次数

        Returns:
            最优超参数字典
        """
        from hyperopt import hp, fmin, tpe, Trials
        import numpy as np

        if max_evals <= 0:
            logger.info("跳过超参数优化（max_evals=0）")
            return {}

        logger.info(f"🔍 开始超参数优化 - 最大评估次数: {max_evals}")

        search_space_config = self.hyperparams.get("search_space", {})
        space = self._build_search_space(search_space_config)
        device = self.hyperparams.get("_device", "auto")

        early_stopping_config = self.hyperparams.get("early_stopping", {})
        early_stop_enabled = early_stopping_config.get("enabled", True)
        patience = early_stopping_config.get("patience", 10)

        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")

        optimization_start = time.time()
        trial_count = [0]
        best_score = [float("inf")]

        def objective(params):
            """优化目标函数."""
            temp_model = None
            try:
                trial_count[0] += 1
                logger.info(f"  Trial {trial_count[0]}/{max_evals} - 参数: {params}")

                temp_hyperparams = {**self.hyperparams, **params}
                # 确保trial epochs最小为10，计算公式：max(10, 配置epochs // 10)
                trial_epochs = max(10, self.hyperparams.get("epochs", 100) // 10)
                temp_hyperparams["epochs"] = trial_epochs
                temp_hyperparams["patience"] = 5
                temp_hyperparams["_device"] = device

                logger.info(
                    f"  Trial {trial_count[0]} 使用 {trial_epochs} epochs（完整训练为 {self.hyperparams.get('epochs', 100)} epochs）"
                )

                temp_model = YOLOClassificationModel(
                    model_name=self.model_name, **temp_hyperparams
                )

                temp_model.fit(train_data, val_data, device=device, log_artifacts=False)

                # 获取训练loss信息
                final_loss = None
                if hasattr(temp_model, "_results") and temp_model._results is not None:
                    try:
                        # YOLO results对象包含训练指标
                        results_dict = (
                            temp_model._results.results_dict
                            if hasattr(temp_model._results, "results_dict")
                            else {}
                        )
                        if "train/loss" in results_dict:
                            final_loss = results_dict["train/loss"]
                        elif hasattr(temp_model._results, "box") and hasattr(
                            temp_model._results.box, "loss"
                        ):
                            final_loss = temp_model._results.box.loss
                    except Exception as e:
                        logger.debug(f"无法获取loss信息: {e}")

                if val_data:
                    val_metrics = temp_model.evaluate(val_data, prefix="val")
                    score = -val_metrics["val_acc_top1"]
                    val_acc_top1 = val_metrics["val_acc_top1"]
                    val_acc_top5 = val_metrics["val_acc_top5"]

                    # 记录结果，包含loss信息
                    loss_info = (
                        f", loss={final_loss:.4f}" if final_loss is not None else ""
                    )
                    logger.info(
                        f"  Trial {trial_count[0]} 结果: top1={val_acc_top1:.4f}, top5={val_acc_top5:.4f}{loss_info}"
                    )

                    if mlflow.active_run():
                        mlflow.log_metric(
                            f"hyperopt/val_acc_top1", val_acc_top1, step=trial_count[0]
                        )
                        mlflow.log_metric(
                            f"hyperopt/val_acc_top5", val_acc_top5, step=trial_count[0]
                        )
                        if final_loss is not None:
                            mlflow.log_metric(
                                f"hyperopt/final_loss", final_loss, step=trial_count[0]
                            )

                        for k, v in params.items():
                            mlflow.log_param(f"trial_{trial_count[0]}_{k}", str(v))

                        if score < best_score[0]:
                            best_score[0] = score
                            mlflow.log_metric(
                                "hyperopt/best_acc_top1",
                                -best_score[0],
                                step=trial_count[0],
                            )

                    return score
                else:
                    train_metrics = temp_model.evaluate(train_data, prefix="train")
                    score = -train_metrics["train_acc_top1"]
                    logger.info(
                        f"  Trial {trial_count[0]} 结果: acc={train_metrics['train_acc_top1']:.4f}"
                    )
                    return score

            except Exception as e:
                logger.error(f"  Trial {trial_count[0]} 失败: {type(e).__name__}: {e}")
                import traceback

                logger.debug(f"完整堆栈:\n{traceback.format_exc()}")
                return 1.0

            finally:
                if temp_model is not None:
                    if hasattr(temp_model, "yolo") and temp_model.yolo is not None:
                        del temp_model.yolo
                    del temp_model

                # Force garbage collection for both CPU and GPU
                import gc

                gc.collect()

                # Clear CUDA cache if available
                if device != "cpu":
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

        # 执行优化
        from hyperopt.early_stop import no_progress_loss

        trials = Trials()
        early_stop_fn = no_progress_loss(patience) if early_stop_enabled else None

        best_params = fmin(
            objective,
            space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=early_stop_fn,
            show_progressbar=False,
        )

        best_params = self._decode_hyperopt_params(best_params, search_space_config)

        optimization_duration = time.time() - optimization_start
        actual_evals = len(trials.trials)
        is_early_stopped = actual_evals < max_evals

        logger.info(f"✓ 超参数优化完成 - 耗时: {optimization_duration / 60:.1f}分钟")
        logger.info(f"  最优参数: {best_params}")
        logger.info(f"  最优得分: {-trials.best_trial['result']['loss']:.4f}")
        logger.info(f"  实际评估次数: {actual_evals}/{max_evals}")

        if mlflow.active_run():
            success_trials = [
                t
                for t in trials.trials
                if t["result"]["status"] == "ok" and t["result"]["loss"] != 1.0
            ]
            failed_trials = [
                t
                for t in trials.trials
                if t["result"]["status"] != "ok" or t["result"]["loss"] == 1.0
            ]

            mlflow.log_metrics(
                {
                    "hyperopt_summary/total_evals": max_evals,
                    "hyperopt_summary/actual_evals": actual_evals,
                    "hyperopt_summary/successful_evals": len(success_trials),
                    "hyperopt_summary/failed_evals": len(failed_trials),
                    "hyperopt_summary/best_acc": -best_score[0],
                    "hyperopt_summary/optimization_duration_min": optimization_duration
                    / 60,
                }
            )

            if early_stop_enabled:
                mlflow.log_metrics(
                    {
                        "hyperopt_summary/early_stop_enabled": 1.0,
                        "hyperopt_summary/early_stopped": 1.0
                        if is_early_stopped
                        else 0.0,
                        "hyperopt_summary/patience": patience,
                    }
                )

        # 将numpy类型转换为Python原生类型（YOLO不接受numpy类型）
        import numpy as np

        converted_params = {}
        for key, value in best_params.items():
            if isinstance(value, np.integer):
                converted_params[key] = int(value)
            elif isinstance(value, np.floating):
                converted_params[key] = float(value)
            elif isinstance(value, np.ndarray):
                converted_params[key] = value.tolist()
            else:
                converted_params[key] = value

        logger.info(
            f"转换后的参数类型: {[(k, type(v).__name__) for k, v in converted_params.items()]}"
        )

        # 更新模型超参数
        self.hyperparams.update(converted_params)

        return converted_params

    def _build_search_space(
        self, search_space_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        根据配置构建Hyperopt搜索空间.

        Args:
            search_space_config: 搜索空间配置字典（格式: {param_name: [value1, value2, ...]}）

        Returns:
            Hyperopt搜索空间
        """
        from hyperopt import hp
        import numpy as np

        if not search_space_config:
            # 使用默认搜索空间
            logger.info("未定义搜索空间，使用默认配置")
            return {
                "lr0": hp.choice("lr0", [0.0001, 0.001, 0.01, 0.05, 0.1]),
                "batch": hp.choice("batch", [8, 16, 32, 64]),
                "imgsz": hp.choice("imgsz", [224, 256, 320]),
            }

        # 从配置构建搜索空间（简化格式：直接用列表）
        space = {}

        for param_name, param_values in search_space_config.items():
            if isinstance(param_values, list) and len(param_values) > 0:
                # hp.choice直接返回列表中的值（不是索引）
                space[param_name] = hp.choice(param_name, param_values)
            elif isinstance(param_values, dict):
                # 兼容旧格式（带type的配置）
                param_type = param_values.get("type", "uniform")

                if param_type == "loguniform":
                    low = param_values.get("low", 0.0001)
                    high = param_values.get("high", 0.1)
                    space[param_name] = hp.loguniform(
                        param_name, np.log(low), np.log(high)
                    )
                elif param_type == "uniform":
                    low = param_values.get("low", 0.0)
                    high = param_values.get("high", 1.0)
                    space[param_name] = hp.uniform(param_name, low, high)
                elif param_type == "quniform":
                    low = param_values.get("low", 0.0)
                    high = param_values.get("high", 1.0)
                    q = param_values.get("q", 1.0)
                    space[param_name] = hp.quniform(param_name, low, high, q)
                elif param_type == "choice":
                    options = param_values.get("options", [])
                    if options:
                        space[param_name] = hp.choice(param_name, options)

        logger.info(f"搜索空间参数: {list(space.keys())}")
        return space

    def _decode_hyperopt_params(
        self, params: Dict[str, Any], search_space_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解码Hyperopt返回的参数（hp.choice返回索引，需转换为实际值）.

        Args:
            params: Hyperopt返回的参数字典（可能包含索引）
            search_space_config: 搜索空间配置

        Returns:
            解码后的参数字典
        """
        # 默认搜索空间（与_build_search_space保持一致）
        default_space = {
            "lr0": [0.0001, 0.001, 0.01, 0.05, 0.1],
            "batch": [8, 16, 32, 64],
            "imgsz": [224, 256, 320],
        }

        import numpy as np

        decoded = {}

        for param_name, value in params.items():
            # 优先使用配置的搜索空间，否则使用默认搜索空间
            param_config = search_space_config.get(param_name) or default_space.get(
                param_name
            )

            # 如果配置是列表格式，且value是索引，转换为实际值
            if isinstance(param_config, list):
                # 支持Python int和numpy整数类型（np.int64, np.int32等）
                if isinstance(value, (int, np.integer)) and 0 <= value < len(
                    param_config
                ):
                    decoded[param_name] = param_config[value]
                else:
                    decoded[param_name] = value
            # 兼容旧的dict格式
            elif (
                isinstance(param_config, dict) and param_config.get("type") == "choice"
            ):
                options = param_config.get("options", [])
                if options and isinstance(value, int) and 0 <= value < len(options):
                    decoded[param_name] = options[value]
                else:
                    decoded[param_name] = value
            else:
                decoded[param_name] = value

        return decoded

    def save_mlflow(self, artifact_path: str = "model"):
        """
        保存模型到MLflow.

        Args:
            artifact_path: MLflow artifact路径
        """
        if self.yolo is None:
            raise RuntimeError("模型未训练，无法保存")

        logger.info("保存YOLO模型到MLflow...")

        # 使用 Path 对象确保跨平台兼容性
        import json
        import tempfile
        import os

        # 创建临时目录用于存放模型文件
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # 保存YOLO权重文件到临时目录
            weights_path = temp_dir / "yolo_best.pt"
            self.yolo.save(str(weights_path))
            logger.info(f"YOLO权重已保存: {weights_path}")

            # 保存类别名称到临时目录
            class_names_path = temp_dir / "class_names.json"
            with open(class_names_path, "w", encoding="utf-8") as f:
                json.dump(self.class_names, f, ensure_ascii=False, indent=2)

            # 创建MLflow pyfunc包装器
            from .yolo_wrapper import YOLOClassificationWrapper

            wrapper = YOLOClassificationWrapper()

            # 记录到MLflow - 使用 str() 确保路径格式正确
            mlflow.pyfunc.log_model(
                artifact_path=artifact_path,
                python_model=wrapper,
                artifacts={
                    "weights": str(weights_path),
                    "class_names": str(class_names_path),
                },
                pip_requirements=[
                    "ultralytics>=8.3.0",
                    "torch>=2.0.0",
                    "torchvision>=0.15.0",
                    "Pillow>=10.0.0",
                ],
            )

            logger.info(f"模型已保存到MLflow: {artifact_path}")

        finally:
            # 清理临时目录和文件
            import shutil

            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"临时目录已清理: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

    def get_params(self) -> Dict[str, Any]:
        """获取模型参数."""
        return {"model_name": self.model_name, **self.hyperparams}

    def _check_fitted(self):
        """检查模型是否已训练."""
        if self.yolo is None:
            raise RuntimeError("模型未训练，请先调用fit()方法")
