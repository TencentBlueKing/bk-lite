"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import base64


class BoundingBox(BaseModel):
    """边界框（Bounding Box）."""

    x1: float = Field(..., description="左上角 X 坐标")
    y1: float = Field(..., description="左上角 Y 坐标")
    x2: float = Field(..., description="右下角 X 坐标")
    y2: float = Field(..., description="右下角 Y 坐标")


class Detection(BaseModel):
    """单个目标检测结果."""

    bbox: BoundingBox = Field(..., description="边界框")
    class_id: int = Field(..., description="类别ID")
    class_name: str = Field(..., description="类别名称")
    confidence: float = Field(..., description="置信度", ge=0.0, le=1.0)


class PredictConfig(BaseModel):
    """预测配置."""

    conf_threshold: float = Field(
        default=0.25,
        description="置信度阈值，低于此值的检测结果将被过滤",
        ge=0.0,
        le=1.0,
    )
    iou_threshold: float = Field(
        default=0.45, description="NMS（非极大值抑制）的 IoU 阈值", ge=0.0, le=1.0
    )
    max_detections: int = Field(
        default=300, description="每张图片返回的最大检测数量", ge=1, le=1000
    )


class PredictRequest(BaseModel):
    """目标检测预测请求（统一批量格式）."""

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
            ["data:image/jpeg;base64,/9j/4AAQ...", "iVBORw0KGgo..."],  # 混合格式批量
        ],
    )

    config: PredictConfig = Field(
        default_factory=PredictConfig, description="预测配置参数"
    )

    @field_validator("images")
    @classmethod
    def validate_images(cls, v: List[str]) -> List[str]:
        """验证base64图片列表."""
        if len(v) > 100:
            raise ValueError(f"批量大小超限：{len(v)} > 100")

        # 快速检查：验证base64格式
        for idx, img_data in enumerate(v):
            if not img_data or len(img_data) < 100:
                raise ValueError(f"图片 {idx} 数据过短，可能无效")

            # 处理Data URI前缀
            test_data = img_data
            if test_data.startswith("data:"):
                # 提取base64部分
                parts = test_data.split(",", 1)
                if len(parts) != 2:
                    raise ValueError(f"图片 {idx} Data URI格式错误")
                test_data = parts[1]

            # 检查base64有效性
            try:
                # 只验证前100字节，确认是有效base64
                base64.b64decode(test_data[:100])
            except Exception:
                raise ValueError(f"图片 {idx} 不是有效的base64编码")

        return v


class ImageResult(BaseModel):
    """单张图片的检测结果."""

    detections: List[Detection] = Field(
        default_factory=list, description="检测结果列表（按置信度降序排列）"
    )

    success: bool = Field(default=True, description="该图片是否处理成功")

    error: Optional[str] = Field(None, description="错误信息（处理失败时）")

    decode_time_ms: Optional[float] = Field(
        None, description="该图片的解码耗时（毫秒）"
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

    # 检测统计
    total_detections: int = Field(..., description="总检测目标数")
    avg_detections_per_image: float = Field(..., description="单张平均检测数")


class ErrorDetail(BaseModel):
    """错误详情."""

    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[dict] = Field(None, description="详细信息")


class PredictResponse(BaseModel):
    """目标检测预测响应（统一批量格式）."""

    results: List[ImageResult] = Field(
        ..., description="预测结果列表，与输入图片一一对应"
    )

    metadata: PredictionMetadata = Field(..., description="预测元数据")

    success: bool = Field(
        default=True, description="是否全部成功（至少一张成功即为True）"
    )

    error: Optional[ErrorDetail] = Field(None, description="整体错误信息（完全失败时）")
