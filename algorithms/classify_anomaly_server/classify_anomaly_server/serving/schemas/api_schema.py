"""Pydantic schemas for request/response validation."""

from typing import Optional
from pydantic import BaseModel, Field
import pandas as pd


class TimeSeriesPoint(BaseModel):
    """时间序列数据点."""

    timestamp: int = Field(..., description="Unix时间戳（秒级）")
    value: float = Field(..., description="观测值")


class DetectionConfig(BaseModel):
    """异常检测配置."""

    threshold: Optional[float] = Field(
        None, description="异常阈值（可选，不提供则使用模型默认阈值）", gt=0.0, le=1.0
    )


class PredictRequest(BaseModel):
    """异常检测请求."""

    data: list[TimeSeriesPoint] = Field(..., description="待检测的时间序列数据")
    config: Optional[DetectionConfig] = Field(None, description="检测配置（可选）")

    def to_series(self) -> pd.Series:
        """转换为 pandas Series，自动处理排序和去重."""
        from loguru import logger

        # 从Unix时间戳（秒级）转换为pd.Timestamp，不带时区（naive datetime）
        timestamps = pd.to_datetime([point.timestamp for point in self.data], unit="s")
        values = [point.value for point in self.data]
        series = pd.Series(values, index=timestamps)

        original_count = len(series)

        # 自动排序（如果未排序）
        if not series.index.is_monotonic_increasing:
            logger.warning(f"⚠️  时间戳未按升序排列，自动排序")
            series = series.sort_index()

        # 去重（如果有重复时间戳，保留最后一个值）
        if series.index.has_duplicates:
            duplicate_count = series.index.duplicated().sum()
            logger.warning(f"⚠️  发现 {duplicate_count} 个重复时间戳，保留最后出现的值")
            series = series[~series.index.duplicated(keep="last")]

        # 记录处理结果
        if len(series) != original_count:
            logger.info(
                f"📊 数据处理: 输入 {original_count} 个点 -> 输出 {len(series)} 个点"
            )

        return series


class AnomalyPoint(BaseModel):
    """异常检测结果点."""

    timestamp: int = Field(..., description="Unix时间戳（秒级）")
    value: float = Field(..., description="原始观测值")
    label: int = Field(..., description="标签: 0=正常, 1=异常")
    anomaly_score: float = Field(..., description="异常分数（越高越异常）")
    anomaly_severity: float = Field(
        ..., description="归一化的异常严重度 [0,1]，基于阈值线性映射，用于展示"
    )


class ResponseMetadata(BaseModel):
    """响应元数据."""

    model_uri: Optional[str] = Field(None, description="模型URI")
    input_data_points: int = Field(..., description="输入数据点数")
    detected_anomalies: int = Field(..., description="检测到的异常点数")
    anomaly_rate: float = Field(..., description="异常率")
    input_frequency: Optional[str] = Field(None, description="检测到的输入频率")
    execution_time_ms: float = Field(..., description="执行耗时（毫秒）")


class ErrorDetail(BaseModel):
    """错误详情."""

    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[dict] = Field(None, description="详细信息")


class PredictResponse(BaseModel):
    """异常检测响应."""

    success: bool = Field(default=True, description="是否成功")
    results: Optional[list[AnomalyPoint]] = Field(None, description="检测结果列表")
    metadata: ResponseMetadata = Field(..., description="响应元数据")
    error: Optional[ErrorDetail] = Field(None, description="错误信息")
