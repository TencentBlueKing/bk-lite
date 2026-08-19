"""Pydantic schemas for request/response validation."""

import os
import re
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from ..metrics import image_budget_exceeded_counter, image_budget_usage

DEFAULT_MAX_IMAGE_BASE64_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES = 96 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_PIXELS = 64 * 1024 * 1024
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]*={0,2}\Z", re.ASCII)
_BASE64_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
_IMAGE_BUDGET_MODES = {"observe", "enforce"}


def _get_positive_int_env(name: str, default: int) -> int:
    """读取正整数资源预算；显式非法配置必须快速失败。"""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive integer") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def get_image_budget_mode() -> str:
    """返回预算模式：observe 保持旧行为，enforce 才拒绝超限请求。"""
    mode = os.getenv("MLOPS_PREDICT_IMAGE_BUDGET_MODE", "observe").strip().lower()
    if mode not in _IMAGE_BUDGET_MODES:
        raise ValueError("MLOPS_PREDICT_IMAGE_BUDGET_MODE must be observe or enforce")
    return mode


def validate_image_budget_config() -> None:
    """在服务初始化时校验完整预算配置。"""
    get_image_budget_mode()
    _get_positive_int_env("MLOPS_PREDICT_MAX_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BASE64_BYTES)
    _get_positive_int_env(
        "MLOPS_PREDICT_MAX_IMAGE_BATCH_BASE64_BYTES",
        DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES,
    )
    _get_positive_int_env("MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", DEFAULT_MAX_IMAGE_BATCH_BYTES)
    get_image_batch_pixel_limit()


def observe_image_budget(dimension: str, value: int, limit: int) -> None:
    """记录资源用量；enforce 模式在超限时拒绝。"""
    mode = get_image_budget_mode()
    image_budget_usage.labels(dimension=dimension).observe(value)
    if value <= limit:
        return
    image_budget_exceeded_counter.labels(dimension=dimension, mode=mode).inc()
    message = f"{dimension}超限：{value} > {limit}"
    logger.warning(f"图片请求预算观测 mode={mode}: {message}")
    if mode == "enforce":
        raise ValueError(message)


def get_image_batch_pixel_limit() -> int:
    """返回单请求允许累计的解码后像素数。"""
    return _get_positive_int_env(
        "MLOPS_PREDICT_MAX_IMAGE_BATCH_PIXELS", DEFAULT_MAX_IMAGE_BATCH_PIXELS
    )


def _get_base64_decoded_size(value: str) -> int:
    """严格校验标准 Base64，并在不物化解码结果时计算字节数。"""
    if len(value) % 4 != 0 or _BASE64_PATTERN.fullmatch(value) is None:
        raise ValueError("不是有效的base64编码")
    padding = len(value) - len(value.rstrip("="))
    return len(value) // 4 * 3 - padding


def _get_legacy_base64_decoded_size(value: str) -> int:
    """按旧宽松 Base64 语义估算字节数，不物化解码副本。"""
    encoded_size = 0
    padding = 0
    for character in value:
        if character not in _BASE64_ALPHABET:
            continue
        encoded_size += 1
        padding = padding + 1 if character == "=" else 0
    if encoded_size % 4 != 0:
        raise ValueError("不是有效的base64编码")
    return encoded_size // 4 * 3 - padding


class ClassPrediction(BaseModel):
    """单个类别预测结果."""
    
    class_id: int = Field(..., description="类别ID")
    class_name: str = Field(..., description="类别名称")
    confidence: float = Field(..., description="置信度", ge=0.0, le=1.0)


class PredictConfig(BaseModel):
    """预测配置."""
    
    top_k: int = Field(
        default=5,
        description="每张图片返回Top-K预测结果",
        ge=1,
        le=20
    )


class PredictRequest(BaseModel):
    """图片分类预测请求（统一批量格式）."""
    
    images: List[str] = Field(
        ...,
        description=(
            "Base64编码的图片列表，支持两种格式：\n"
            "1. 纯base64: 'iVBORw0KGgo...'\n"
            "2. Data URI: 'data:image/jpeg;base64,/9j/4AAQ...'\n"
            "支持单张和批量预测"
        ),
        min_length=1,
        max_length=100,
        examples=[
            ["iVBORw0KGgo..."],  # 纯base64单张
            ["data:image/jpeg;base64,/9j/4AAQ...", "iVBORw0KGgo..."]  # 混合格式批量
        ]
    )
    
    config: PredictConfig = Field(
        default_factory=PredictConfig,
        description="预测配置参数"
    )
    
    @field_validator('images')
    @classmethod
    def validate_images(cls, v: List[str]) -> List[str]:
        """验证base64图片列表."""
        if len(v) > 100:
            raise ValueError(f"批量大小超限：{len(v)} > 100")

        max_image_bytes = _get_positive_int_env(
            "MLOPS_PREDICT_MAX_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BASE64_BYTES
        )
        max_batch_base64_bytes = _get_positive_int_env(
            "MLOPS_PREDICT_MAX_IMAGE_BATCH_BASE64_BYTES",
            DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES,
        )
        max_batch_bytes = _get_positive_int_env(
            "MLOPS_PREDICT_MAX_IMAGE_BATCH_BYTES", DEFAULT_MAX_IMAGE_BATCH_BYTES
        )
        total_encoded_bytes = sum(len(img_data) for img_data in v)
        observe_image_budget("批次编码量", total_encoded_bytes, max_batch_base64_bytes)
        total_decoded_bytes = 0
        
        for idx, img_data in enumerate(v):
            if not img_data or len(img_data) < 100:
                raise ValueError(f"图片 {idx} 数据过短，可能无效")
            try:
                observe_image_budget("单图编码量", len(img_data), max_image_bytes)
            except ValueError as exc:
                raise ValueError(f"图片 {idx} {exc}") from None

            if not img_data.isascii():
                error = (
                    "Data URI格式错误"
                    if img_data.startswith("data:")
                    else "不是有效的base64编码"
                )
                raise ValueError(f"图片 {idx} {error}")

            # 处理Data URI前缀
            test_data = img_data
            if test_data.startswith('data:'):
                # 提取base64部分
                parts = test_data.split(',', 1)
                if len(parts) != 2:
                    raise ValueError(f"图片 {idx} Data URI格式错误")
                header = parts[0].lower()
                if get_image_budget_mode() == "enforce" and (
                    not header.startswith("data:image/")
                    or not header.endswith(";base64")
                ):
                    raise ValueError(f"图片 {idx} Data URI格式错误")
                test_data = parts[1]

            try:
                observe_image_budget("单图Base64编码量", len(test_data), max_image_bytes)
            except ValueError as exc:
                raise ValueError(f"图片 {idx} {exc}") from None

            if get_image_budget_mode() == "enforce":
                try:
                    decoded_size = _get_base64_decoded_size(test_data)
                except ValueError:
                    raise ValueError(f"图片 {idx} 不是有效的base64编码") from None
            else:
                try:
                    decoded_size = _get_legacy_base64_decoded_size(test_data)
                except ValueError:
                    raise ValueError(f"图片 {idx} 不是有效的base64编码") from None

            total_decoded_bytes += decoded_size
            observe_image_budget("批次解码字节量", total_decoded_bytes, max_batch_bytes)
        
        return v


class ImageResult(BaseModel):
    """单张图片的预测结果."""
    
    predictions: List[ClassPrediction] = Field(
        default_factory=list,
        description="Top-K预测结果（按置信度降序排列）"
    )
    
    success: bool = Field(
        default=True,
        description="该图片是否处理成功"
    )
    
    error: Optional[str] = Field(
        None,
        description="错误信息（处理失败时）"
    )
    
    decode_time_ms: Optional[float] = Field(
        None,
        description="该图片的解码耗时（毫秒）"
    )


class PredictionMetadata(BaseModel):
    """预测元数据."""
    
    model_version: str = Field(..., description="模型版本或路径")
    source: str = Field(..., description="模型来源：local/mlflow/dummy")
    batch_size: int = Field(..., description="批量大小")
    
    # 时间统计
    total_time_ms: float = Field(..., description="总耗时（毫秒）")
    decode_time_ms: float = Field(..., description="解码阶段总耗时")
    predict_time_ms: float = Field(..., description="预测阶段耗时")
    postprocess_time_ms: float = Field(..., description="后处理耗时")
    avg_time_per_image_ms: float = Field(..., description="单张平均耗时")
    
    # 成功率统计
    success_count: int = Field(..., description="成功处理的图片数")
    failure_count: int = Field(..., description="失败的图片数")
    success_rate: float = Field(..., description="成功率", ge=0.0, le=1.0)


class ErrorDetail(BaseModel):
    """错误详情."""
    
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[dict] = Field(None, description="详细信息")


class PredictResponse(BaseModel):
    """图片分类预测响应（统一批量格式）."""
    
    results: List[ImageResult] = Field(
        ...,
        description="预测结果列表，与输入图片一一对应"
    )
    
    metadata: PredictionMetadata = Field(
        ...,
        description="预测元数据"
    )
    
    success: bool = Field(
        default=True,
        description="是否全部成功（至少一张成功即为True）"
    )
    
    error: Optional[ErrorDetail] = Field(
        None,
        description="整体错误信息（完全失败时）"
    )
