"""YOLO目标检测模型封装."""

from typing import Dict, Any, Optional, List
from pathlib import Path
import mlflow
from loguru import logger
from ultralytics import YOLO, settings
import uuid
import time

from classify_object_detection_server import PROJECT_ROOT
from .base import BaseObjectDetectionModel, ModelRegistry

# 禁用YOLO的MLflow自动集成，避免与自定义MLflow管理冲突
settings.update({"mlflow": False})
logger.info("已禁用YOLO的MLflow自动集成")


@ModelRegistry.register("YOLOv11Detection")
class YOLOv11DetectionModel(BaseObjectDetectionModel):
    """YOLO目标检测模型.

    封装ultralytics YOLOv11检测模型，实现统一的训练和推理接口。
    """

    def __init__(self, model_name: str = "yolo11n.pt", **hyperparams):
        """
        初始化YOLO检测模型.

        Args:
            model_name: YOLO模型名称（如 'yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt' 等）
            **hyperparams: 其他超参数
        """
        self.model_name = model_name
        self.hyperparams = hyperparams
        self.yolo = None
        self.class_names = None
        self._results = None

        logger.info(f"YOLOv11DetectionModel初始化: {self.model_name}")

    def fit(
        self,
        dataset_yaml: str,
        val_data: Optional[str] = None,
        device: str = "auto",
        log_artifacts: bool = True,
        **kwargs,
    ) -> "YOLOv11DetectionModel":
        """
        训练YOLO检测模型.

        Args:
            dataset_yaml: YOLO格式数据集配置文件路径
            val_data: 验证集配置（可选，通常已包含在dataset_yaml中）
            device: 设备配置
            log_artifacts: 是否上传训练产生的artifacts到MLflow，默认True
            **kwargs: 额外训练参数

        Returns:
            self
        """
        logger.info(f"开始训练YOLO检测模型，设备: {device}")
        logger.info(f"数据集配置: {dataset_yaml}")

        # 初始化YOLO检测模型
        self.yolo = YOLO(self.model_name)

        # 构建训练参数
        train_kwargs = {
            "data": dataset_yaml,
            "epochs": self.hyperparams.get("epochs", 100),
            "imgsz": self.hyperparams.get("imgsz", 640),
            "batch": self.hyperparams.get("batch", 16),
            "lr0": self.hyperparams.get("lr0", 0.01),
            "lrf": self.hyperparams.get("lrf", 0.01),
            "momentum": self.hyperparams.get("momentum", 0.937),
            "weight_decay": self.hyperparams.get("weight_decay", 0.0005),
            "warmup_epochs": self.hyperparams.get("warmup_epochs", 3.0),
            "optimizer": self.hyperparams.get("optimizer", "SGD"),
            "amp": self.hyperparams.get("amp", True),
            "patience": self.hyperparams.get("patience", 50),
            "device": device,
            "project": PROJECT_ROOT / ".yolo_runs" / "detection_training",
            "name": f"train_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "save": True,
            "plots": True,
            "verbose": False,
        }

        # 添加数据增强参数（如果启用）
        if self.hyperparams.get("augment") is False:
            train_kwargs["augment"] = False
        else:
            # 几何变换参数
            for aug_param in [
                "degrees",
                "translate",
                "scale",
                "shear",
                "perspective",
                "fliplr",
                "flipud",
            ]:
                if aug_param in self.hyperparams:
                    train_kwargs[aug_param] = self.hyperparams[aug_param]

            # 颜色增强参数
            for aug_param in ["hsv_h", "hsv_s", "hsv_v"]:
                if aug_param in self.hyperparams:
                    train_kwargs[aug_param] = self.hyperparams[aug_param]

            # 检测专用高级增强
            for aug_param in ["mosaic", "mixup", "copy_paste"]:
                if aug_param in self.hyperparams:
                    train_kwargs[aug_param] = self.hyperparams[aug_param]

        if device != "cpu" and self.hyperparams.get("amp", True):
            train_kwargs["amp"] = True
            logger.info("⚡ 启用混合精度训练（AMP）")

        # 执行训练
        logger.info(
            f"🚀 开始训练 - epochs={train_kwargs['epochs']}, batch={train_kwargs['batch']}, imgsz={train_kwargs['imgsz']}"
        )
        logger.info(f"📁 输出目录: {train_kwargs['project']}/{train_kwargs['name']}")

        train_start_time = time.time()
        results = self.yolo.train(**train_kwargs)
        train_duration = time.time() - train_start_time

        self._results = results

        # 记录训练指标
        loss_info = ""
        try:
            if hasattr(results, "results_dict") and results.results_dict:
                results_dict = results.results_dict
                # 检测模型的loss包含: box_loss, cls_loss, dfl_loss
                box_loss = results_dict.get("train/box_loss")
                cls_loss = results_dict.get("train/cls_loss")
                dfl_loss = results_dict.get("train/dfl_loss")

                if box_loss is not None:
                    loss_info = f", box_loss={box_loss:.4f}"
                    if cls_loss is not None:
                        loss_info += f", cls_loss={cls_loss:.4f}"
                    if dfl_loss is not None:
                        loss_info += f", dfl_loss={dfl_loss:.4f}"
                    logger.info(f"📊 训练loss{loss_info}")
        except Exception as e:
            logger.debug(f"无法获取loss信息: {e}")

        logger.info(f"✓ 训练完成 - 耗时: {train_duration / 60:.1f}分钟{loss_info}")

        # 手动上传YOLO训练产生的artifacts到MLflow
        if log_artifacts:
            self._log_yolo_artifacts_to_mlflow(train_kwargs)
        else:
            # 超参数优化时也要清理临时文件
            self._cleanup_yolo_output(train_kwargs)

        return self

    def predict(self, X: Any) -> List[Dict[str, Any]]:
        """
        批量预测.

        Args:
            X: 图片路径列表、PIL Image列表或numpy数组

        Returns:
            预测结果列表，每个元素格式:
            {
                'boxes': [[x1, y1, x2, y2], ...],  # 归一化坐标
                'classes': [class_id, ...],
                'confidences': [conf, ...],
                'labels': [label_name, ...]
            }
        """
        if self.yolo is None:
            raise RuntimeError("模型未训练，请先调用fit()方法")

        results = self.yolo.predict(
            X,
            imgsz=self.hyperparams.get("imgsz", 640),
            conf=self.hyperparams.get("conf", 0.25),
            iou=self.hyperparams.get("iou", 0.45),
            verbose=False,
        )

        # 解析预测结果
        predictions = []
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                predictions.append(
                    {"boxes": [], "classes": [], "confidences": [], "labels": []}
                )
                continue

            boxes = (
                result.boxes.xyxyn.cpu().numpy().tolist()
            )  # 归一化坐标 [x1, y1, x2, y2]
            classes = result.boxes.cls.cpu().numpy().astype(int).tolist()
            confidences = result.boxes.conf.cpu().numpy().tolist()
            labels = [result.names[cls_id] for cls_id in classes]

            predictions.append(
                {
                    "boxes": boxes,
                    "classes": classes,
                    "confidences": confidences,
                    "labels": labels,
                }
            )

        return predictions

    def evaluate(
        self, test_data: str, prefix: str = "test", log_artifacts: bool = False
    ) -> Dict[str, float]:
        """
        评估模型性能.

        Args:
            test_data: 测试数据集配置文件路径（YOLO格式）
            prefix: 指标前缀
            log_artifacts: 是否上传评估产生的artifacts到MLflow，默认False

        Returns:
            评估指标字典，包含mAP、precision、recall等
        """
        if self.yolo is None:
            raise RuntimeError("模型未训练")

        logger.info(f"在{prefix}集上评估模型: {test_data}")

        eval_kwargs = {
            "data": test_data,
            "split": prefix,
            "verbose": False,
            "save_json": True,  # 保存COCO格式的结果
            "save": True,
            "plots": True,
            "project": PROJECT_ROOT / ".yolo_runs" / "detection_validation",
            "name": f"eval_{prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}",
        }

        metrics = self.yolo.val(**eval_kwargs)

        # 提取检测指标
        eval_results = {
            f"{prefix}_map50": float(metrics.box.map50),  # mAP@0.5
            f"{prefix}_map": float(metrics.box.map),  # mAP@0.5:0.95
            f"{prefix}_precision": float(metrics.box.mp),  # mean precision
            f"{prefix}_recall": float(metrics.box.mr),  # mean recall
        }

        # 可选：记录每个类别的指标（不上传到MLflow）
        if hasattr(metrics.box, "ap_class_index") and hasattr(metrics.box, "ap"):
            eval_results["_per_class_metrics"] = {
                "class_indices": metrics.box.ap_class_index.tolist(),
                "ap_per_class": metrics.box.ap.tolist(),
            }

        logger.info(
            f"评估完成: mAP50={eval_results[f'{prefix}_map50']:.4f}, "
            f"mAP={eval_results[f'{prefix}_map']:.4f}, "
            f"precision={eval_results[f'{prefix}_precision']:.4f}, "
            f"recall={eval_results[f'{prefix}_recall']:.4f}"
        )

        if log_artifacts:
            self._log_yolo_eval_artifacts_to_mlflow(eval_kwargs, prefix)
        else:
            self._cleanup_yolo_output(eval_kwargs)

        return eval_results

    def _log_yolo_artifacts_to_mlflow(self, train_kwargs: Dict[str, Any]):
        """
        手动上传YOLO训练产生的artifacts到MLflow.

        Args:
            train_kwargs: 训练参数，包含project和name
        """
        import shutil

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
                "confusion_matrix_normalized.png",
            ]

            for filename in files_to_upload:
                file_path = save_dir / filename
                if file_path.exists():
                    logger.debug(f"上传文件: {filename}")
                    mlflow.log_artifact(str(file_path))

            # 上传训练过程的可视化图片
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

    def _log_yolo_eval_artifacts_to_mlflow(
        self, eval_kwargs: Dict[str, Any], prefix: str = "test"
    ):
        """
        手动上传YOLO评估产生的artifacts到MLflow.

        Args:
            eval_kwargs: 评估参数
            prefix: 评估前缀
        """
        import shutil

        save_dir = Path(eval_kwargs["project"]) / eval_kwargs["name"]

        if not save_dir.exists():
            logger.warning(f"YOLO评估输出目录不存在: {save_dir}")
            return

        logger.info(f"开始上传YOLO评估artifacts到MLflow: {save_dir}")

        try:
            artifact_path = f"{prefix}_evaluation"

            files_to_upload = [
                "confusion_matrix.png",
                "confusion_matrix_normalized.png",
                "PR_curve.png",  # Precision-Recall曲线
                "F1_curve.png",  # F1曲线
            ]

            for filename in files_to_upload:
                file_path = save_dir / filename
                if file_path.exists():
                    logger.debug(f"上传文件: {filename}")
                    mlflow.log_artifact(str(file_path), artifact_path=artifact_path)

            # 上传预测样例图片
            for img_file in save_dir.glob("*.jpg"):
                logger.debug(f"上传图片: {img_file.name}")
                mlflow.log_artifact(str(img_file), artifact_path=artifact_path)

            for img_file in save_dir.glob("*.png"):
                if img_file.name not in files_to_upload:
                    logger.debug(f"上传图片: {img_file.name}")
                    mlflow.log_artifact(str(img_file), artifact_path=artifact_path)

            logger.info(f"✓ YOLO评估artifacts上传完成（目录: {artifact_path}）")

            self._cleanup_yolo_output(eval_kwargs)

        except Exception as e:
            logger.error(f"上传评估artifacts到MLflow失败: {e}")

    def _cleanup_yolo_output(self, train_kwargs: Dict[str, Any]):
        """清理YOLO训练/评估输出目录."""
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
        self, train_data: str, val_data: str, max_evals: int
    ) -> Dict[str, Any]:
        """
        超参数优化（使用Hyperopt）.

        Args:
            train_data: 训练数据集配置文件路径
            val_data: 验证数据集配置文件路径
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
                # trial使用较少的epochs进行快速评估
                trial_epochs = max(10, self.hyperparams.get("epochs", 100) // 10)
                temp_hyperparams["epochs"] = trial_epochs
                temp_hyperparams["patience"] = 5
                temp_hyperparams["_device"] = device

                logger.info(f"  Trial {trial_count[0]} 使用 {trial_epochs} epochs")

                temp_model = YOLOv11DetectionModel(
                    size=self.model_size, **temp_hyperparams
                )

                temp_model.fit(train_data, val_data, device=device, log_artifacts=False)

                # 在验证集上评估
                val_metrics = temp_model.evaluate(val_data, prefix="val")
                # 使用mAP@0.5:0.95作为优化目标（取负数用于最小化）
                score = -val_metrics["val_map"]

                logger.info(
                    f"  Trial {trial_count[0]} 结果: "
                    f"mAP={val_metrics['val_map']:.4f}, "
                    f"mAP50={val_metrics['val_map50']:.4f}, "
                    f"precision={val_metrics['val_precision']:.4f}, "
                    f"recall={val_metrics['val_recall']:.4f}"
                )

                if mlflow.active_run():
                    mlflow.log_metric(
                        f"hyperopt/val_map", val_metrics["val_map"], step=trial_count[0]
                    )
                    mlflow.log_metric(
                        f"hyperopt/val_map50",
                        val_metrics["val_map50"],
                        step=trial_count[0],
                    )
                    mlflow.log_metric(
                        f"hyperopt/val_precision",
                        val_metrics["val_precision"],
                        step=trial_count[0],
                    )
                    mlflow.log_metric(
                        f"hyperopt/val_recall",
                        val_metrics["val_recall"],
                        step=trial_count[0],
                    )

                    for k, v in params.items():
                        mlflow.log_param(f"trial_{trial_count[0]}_{k}", str(v))

                    if score < best_score[0]:
                        best_score[0] = score
                        mlflow.log_metric(
                            "hyperopt/best_map", -best_score[0], step=trial_count[0]
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
        logger.info(f"  最优mAP: {-trials.best_trial['result']['loss']:.4f}")
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
                    "hyperopt_summary/best_map": -best_score[0],
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

        # 将numpy类型转换为Python原生类型
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
        """根据配置构建Hyperopt搜索空间."""
        from hyperopt import hp
        import numpy as np

        if not search_space_config:
            # 使用默认搜索空间（检测任务常用参数）
            logger.info("未定义搜索空间，使用默认配置")
            return {
                "lr0": hp.choice("lr0", [0.001, 0.01, 0.05]),
                "batch": hp.choice("batch", [8, 16, 32]),
                "imgsz": hp.choice("imgsz", [416, 512, 640]),
            }

        # 从配置构建搜索空间
        space = {}

        for param_name, param_values in search_space_config.items():
            if isinstance(param_values, list) and len(param_values) > 0:
                space[param_name] = hp.choice(param_name, param_values)
            elif isinstance(param_values, dict):
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
        """解码Hyperopt返回的参数."""
        default_space = {
            "lr0": [0.001, 0.01, 0.05],
            "batch": [8, 16, 32],
            "imgsz": [416, 512, 640],
        }

        import numpy as np

        decoded = {}

        for param_name, value in params.items():
            param_config = search_space_config.get(param_name) or default_space.get(
                param_name
            )

            if isinstance(param_config, list):
                if isinstance(value, (int, np.integer)) and 0 <= value < len(
                    param_config
                ):
                    decoded[param_name] = param_config[value]
                else:
                    decoded[param_name] = value
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

        logger.info("保存YOLO检测模型到MLflow...")

        # 保存YOLO权重文件
        weights_path = "yolo_detection_best.pt"
        self.yolo.save(weights_path)
        logger.info(f"YOLO权重已保存: {weights_path}")

        # 创建MLflow pyfunc包装器
        from .yolo_wrapper import YOLODetectionWrapper

        wrapper = YOLODetectionWrapper()

        # 保存类别名称到文件
        import json

        class_names_path = "class_names.json"
        # 从模型中提取类别名称
        class_names = self.yolo.names if hasattr(self.yolo, "names") else None
        if class_names:
            # YOLO的names是字典格式 {0: 'person', 1: 'car', ...}
            # 转换为列表格式
            if isinstance(class_names, dict):
                class_names_list = [class_names[i] for i in sorted(class_names.keys())]
            else:
                class_names_list = list(class_names)

            with open(class_names_path, "w", encoding="utf-8") as f:
                json.dump(class_names_list, f, ensure_ascii=False, indent=2)

        # 记录到MLflow
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=wrapper,
            artifacts={"weights": weights_path, "class_names": class_names_path},
            pip_requirements=[
                "ultralytics>=8.3.0",
                "torch>=2.0.0",
                "torchvision>=0.15.0",
                "Pillow>=10.0.0",
            ],
        )

        logger.info(f"模型已保存到MLflow: {artifact_path}")

        # 清理临时文件
        import os

        try:
            os.remove(weights_path)
            os.remove(class_names_path)
            logger.debug("临时文件已清理")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")

    def get_params(self) -> Dict[str, Any]:
        """获取模型参数."""
        return {
            "model_size": self.model_size,
            "model_name": self.model_name,
            **self.hyperparams,
        }

    def _check_fitted(self):
        """检查模型是否已训练."""
        if self.yolo is None:
            raise RuntimeError("模型未训练，请先调用fit()方法")
