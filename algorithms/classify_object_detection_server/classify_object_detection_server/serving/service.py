"""BentoML service definition."""

import bentoml
from loguru import logger
import base64
from io import BytesIO
from PIL import Image
import time

from .config import get_model_config
from .exceptions import ModelInferenceError
from .metrics import (
    health_check_counter,
    model_load_counter,
    prediction_counter,
    prediction_duration,
    detection_counter,
)
from .models import load_model
from .schemas import (
    PredictRequest,
    PredictResponse,
    Detection,
    BoundingBox,
    ImageResult,
    PredictionMetadata,
    ErrorDetail,
)


@bentoml.service(
    name="classify_object_detection_service",
    traffic={"timeout": 30},
)
class MLService:
    """目标检测模型服务."""

    @bentoml.on_deployment
    def setup() -> None:
        """
        部署时执行一次的全局初始化.

        用于预热缓存、下载资源等全局操作.
        不接收 self 参数,类似静态方法.
        """
        logger.info("=== Deployment setup started ===")
        # 可以在这里做全局初始化,例如:
        # - 预热模型缓存
        # - 下载共享资源
        # - 初始化全局连接池
        logger.info("=== Deployment setup completed ===")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.info("Service instance initializing...")
        self.config = get_model_config()
        logger.info(f"Config loaded: {self.config}")

        try:
            self.model = load_model(self.config)
            model_load_counter.labels(source=self.config.source, status="success").inc()
            logger.info("Model loaded successfully")
        except Exception as e:
            model_load_counter.labels(source=self.config.source, status="failure").inc()
            logger.error(f"Failed to load model: {e}")
            raise

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        logger.info("=== Service shutdown: cleaning up resources ===")
        # 清理逻辑,例如:
        # - 关闭数据库连接
        # - 保存缓存状态
        # - 释放 GPU 显存
        logger.info("=== Cleanup completed ===")

    def _decode_base64_image(self, img_data: str) -> Image.Image:
        """
        解码base64图片，支持纯base64和Data URI格式.

        Args:
            img_data: Base64编码的图片数据

        Returns:
            PIL Image对象

        Raises:
            ValueError: 图片格式或尺寸不合法
        """
        # 移除Data URI前缀（如果存在）
        if img_data.startswith("data:"):
            # 提取base64部分：data:image/jpeg;base64,xxxxx -> xxxxx
            img_data = img_data.split(",", 1)[1]

        # 解码base64
        image_bytes = base64.b64decode(img_data)

        # 加载PIL图片
        image = Image.open(BytesIO(image_bytes))

        # 验证格式
        if image.format not in ["JPEG", "PNG", "BMP", "WEBP", None]:
            raise ValueError(f"不支持的图片格式: {image.format}")

        # 验证尺寸
        if max(image.size) > 4096:
            raise ValueError(f"图片过大: {image.size}, 最大4096px")

        # 转换为RGB（YOLO要求）
        if image.mode != "RGB":
            image = image.convert("RGB")

        return image

    @bentoml.api
    async def predict(
        self, images: list, config: dict | None = None
    ) -> PredictResponse:
        """
        目标检测预测接口（统一批量格式）.

        支持单张和批量预测，自动利用YOLO批处理优化GPU利用率。

        示例：
            单张：{"images": ["base64..."], "config": {"conf_threshold": 0.25}}
            批量：{"images": ["img1", "img2", ...], "config": {"conf_threshold": 0.5}}

        Args:
            images: Base64编码的图片列表
            config: 预测配置（可选）

        Returns:
            预测响应，results与输入images一一对应
        """
        from .schemas import PredictConfig

        request_start = time.time()

        # 构造请求对象进行验证
        try:
            predict_config = PredictConfig(**config) if config else PredictConfig()
            request = PredictRequest(images=images, config=predict_config)
        except Exception as e:
            logger.error(f"Request validation failed: {e}")
            return PredictResponse(
                results=[],
                metadata=PredictionMetadata(
                    model_version="unknown",
                    source=self.config.source,
                    batch_size=0,
                    total_time_ms=(time.time() - request_start) * 1000,
                    decode_time_ms=0.0,
                    predict_time_ms=0.0,
                    postprocess_time_ms=0.0,
                    avg_time_per_image_ms=0.0,
                    success_count=0,
                    failure_count=0,
                    success_rate=0.0,
                    total_detections=0,
                    avg_detections_per_image=0.0,
                ),
                success=False,
                error=ErrorDetail(
                    code="E1000",
                    message=f"请求格式验证失败: {str(e)}",
                    details={"error_type": type(e).__name__},
                ),
            )

        batch_size = len(request.images)

        logger.info(
            f"📥 Received detection request: batch_size={batch_size}, "
            f"conf={request.config.conf_threshold}, iou={request.config.iou_threshold}"
        )

        # ========== 阶段1：批量解码 ==========
        decode_start = time.time()
        decoded_images = []
        decode_times = []
        decode_errors = []

        for idx, img_data in enumerate(request.images):
            img_decode_start = time.time()
            try:
                image = self._decode_base64_image(img_data)
                decoded_images.append(image)
                decode_times.append((time.time() - img_decode_start) * 1000)
                decode_errors.append(None)
                logger.debug(f"✅ Image {idx} decoded: {image.size}, {image.mode}")

            except Exception as e:
                logger.warning(f"⚠️  Image {idx} decode failed: {e}")
                decoded_images.append(None)
                decode_times.append((time.time() - img_decode_start) * 1000)
                decode_errors.append(str(e))

        total_decode_time = time.time() - decode_start

        # 统计有效图片
        valid_indices = [i for i, img in enumerate(decoded_images) if img is not None]
        valid_images = [decoded_images[i] for i in valid_indices]
        valid_count = len(valid_images)
        failure_count = batch_size - valid_count

        logger.info(
            f"📊 Decode completed: success={valid_count}, "
            f"failed={failure_count}, time={total_decode_time:.3f}s"
        )

        # 全部解码失败，提前返回
        if not valid_images:
            logger.error("❌ All images decode failed")
            return PredictResponse(
                results=[
                    ImageResult(
                        detections=[],
                        success=False,
                        error=decode_errors[i],
                        decode_time_ms=decode_times[i],
                    )
                    for i in range(batch_size)
                ],
                metadata=PredictionMetadata(
                    model_version=self.config.model_path or "unknown",
                    source=self.config.source,
                    batch_size=batch_size,
                    total_time_ms=(time.time() - request_start) * 1000,
                    decode_time_ms=total_decode_time * 1000,
                    predict_time_ms=0.0,
                    postprocess_time_ms=0.0,
                    avg_time_per_image_ms=0.0,
                    success_count=0,
                    failure_count=batch_size,
                    success_rate=0.0,
                    total_detections=0,
                    avg_detections_per_image=0.0,
                ),
                success=False,
                error=ErrorDetail(
                    code="E1001",
                    message="所有图片解码失败",
                    details={"errors": decode_errors},
                ),
            )

        # ========== 阶段2：批量预测 ==========
        logger.info(
            f"🤖 Starting detection: {valid_count} valid images, "
            f"model_source={self.config.source}"
        )

        predict_start = time.time()
        predictions = None
        predict_error = None

        try:
            # 构造模型输入（包含推理参数）
            model_input = {
                "images": valid_images,
                "conf": request.config.conf_threshold,
                "iou": request.config.iou_threshold,
            }

            # 调用模型预测（返回格式见 YOLOWrapper）
            predictions = self.model.predict(model_input)
            predict_time = time.time() - predict_start

            logger.info("✅ Detection completed successfully")
            logger.info(
                f"⏱️  Detection time: {predict_time:.3f}s, {valid_count} images, "
                f"{predict_time / valid_count:.3f}s per image"
            )

        except Exception as e:
            predict_time = time.time() - predict_start
            predict_error = str(e)

            logger.error(f"❌ Detection failed: {e}", exc_info=True)

            # 预测失败，标记所有有效图片为失败
            return PredictResponse(
                results=[
                    ImageResult(
                        detections=[],
                        success=False,
                        error=predict_error if i in valid_indices else decode_errors[i],
                        decode_time_ms=decode_times[i],
                    )
                    for i in range(batch_size)
                ],
                metadata=PredictionMetadata(
                    model_version=self.config.model_path or "unknown",
                    source=self.config.source,
                    batch_size=batch_size,
                    total_time_ms=(time.time() - request_start) * 1000,
                    decode_time_ms=total_decode_time * 1000,
                    predict_time_ms=predict_time * 1000,
                    postprocess_time_ms=0.0,
                    avg_time_per_image_ms=0.0,
                    success_count=0,
                    failure_count=batch_size,
                    success_rate=0.0,
                    total_detections=0,
                    avg_detections_per_image=0.0,
                ),
                success=False,
                error=ErrorDetail(
                    code="E2001",
                    message=f"模型检测失败: {predict_error}",
                    details={"model_source": self.config.source},
                ),
            )

        # ========== 阶段3：后处理和组装结果 ==========
        postprocess_start = time.time()

        results = []
        pred_idx = 0
        total_detections = 0

        for idx in range(batch_size):
            if decode_errors[idx]:
                # 解码失败的图片
                results.append(
                    ImageResult(
                        detections=[],
                        success=False,
                        error=decode_errors[idx],
                        decode_time_ms=decode_times[idx],
                    )
                )
            else:
                # 解码成功的图片，提取检测结果
                pred = predictions[pred_idx]

                # 转换为 Detection 对象列表
                # pred 格式: {'boxes': [[x1,y1,x2,y2], ...], 'classes': [...], 'confidences': [...], 'labels': [...]}
                detections = []
                for i in range(len(pred["boxes"])):
                    box = pred["boxes"][i]
                    detection = Detection(
                        bbox=BoundingBox(x1=box[0], y1=box[1], x2=box[2], y2=box[3]),
                        class_id=pred["classes"][i],
                        class_name=pred["labels"][i],
                        confidence=pred["confidences"][i],
                    )
                    detections.append(detection)

                # 应用 max_detections 限制
                if len(detections) > request.config.max_detections:
                    detections = detections[: request.config.max_detections]

                total_detections += len(detections)

                results.append(
                    ImageResult(
                        detections=detections,
                        success=True,
                        error=None,
                        decode_time_ms=decode_times[idx],
                    )
                )
                pred_idx += 1

        postprocess_time = time.time() - postprocess_start

        # ========== 阶段4：元数据统计 ==========
        total_time = time.time() - request_start
        success_count = sum(1 for r in results if r.success)
        failure_count = batch_size - success_count

        metadata = PredictionMetadata(
            model_version=self.config.model_path or "unknown",
            source=self.config.source,
            batch_size=batch_size,
            total_time_ms=total_time * 1000,
            decode_time_ms=total_decode_time * 1000,
            predict_time_ms=predict_time * 1000,
            postprocess_time_ms=postprocess_time * 1000,
            avg_time_per_image_ms=(predict_time * 1000) / valid_count
            if valid_count > 0
            else 0.0,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_count / batch_size,
            total_detections=total_detections,
            avg_detections_per_image=total_detections / success_count
            if success_count > 0
            else 0.0,
        )

        # 更新Prometheus指标
        if success_count > 0:
            prediction_counter.labels(
                model_source=self.config.source, status="success"
            ).inc(success_count)
            detection_counter.labels(model_source=self.config.source).inc(
                total_detections
            )

        if failure_count > 0:
            prediction_counter.labels(
                model_source=self.config.source, status="failure"
            ).inc(failure_count)

        logger.info(
            f"✅ Request completed: success={success_count}/{batch_size} "
            f"({metadata.success_rate:.1%}), total_detections={total_detections}, "
            f"total_time={total_time:.3f}s"
        )

        return PredictResponse(
            results=results, metadata=metadata, success=(success_count > 0), error=None
        )

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
