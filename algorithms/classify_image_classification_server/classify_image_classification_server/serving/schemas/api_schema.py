"""Pydantic schemas for request/response validation."""

import os
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

DEFAULT_MAX_IMAGE_BASE64_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_BASE64_BYTES = 96 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_IMAGE_BATCH_PIXELS = 64 * 1024 * 1024
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]*={0,2}\Z", re.ASCII)


def _get_positive_int_env(name: str, default: int) -> int:
    """读取正整数资源预算，非法配置安全回退到默认值。"""
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


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
        if total_encoded_bytes > max_batch_base64_bytes:
            raise ValueError(
                f"批次编码量超限：{total_encoded_bytes} > {max_batch_base64_bytes}"
            )
        total_decoded_bytes = 0
        
        for idx, img_data in enumerate(v):
            if not img_data or len(img_data) < 100:
                raise ValueError(f"图片 {idx} 数据过短，可能无效")
            if len(img_data) > max_image_bytes:
                raise ValueError(
                    f"图片 {idx} 单图编码量超限：{len(img_data)} > {max_image_bytes}"
                )

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
                header = parts[0].lower()
                if (
                    len(parts) != 2
                    or not header.startswith("data:image/")
                    or not header.endswith(";base64")
                ):
                    raise ValueError(f"图片 {idx} Data URI格式错误")
                test_data = parts[1]

            if len(test_data) > max_image_bytes:
                raise ValueError(
                    f"图片 {idx} 单图编码量超限：{len(test_data)} > {max_image_bytes}"
                )

            try:
                decoded_size = _get_base64_decoded_size(test_data)
            except ValueError:
                raise ValueError(f"图片 {idx} 不是有效的base64编码") from None

            total_decoded_bytes += decoded_size
            if total_decoded_bytes > max_batch_bytes:
                raise ValueError(
                    "批次解码字节量超限："
                    f"{total_decoded_bytes} > {max_batch_bytes}"
                )
        
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
