"""Pydantic schemas for request/response validation."""

from typing import Optional
from pydantic import BaseModel, Field
import pandas as pd


class TimeSeriesPoint(BaseModel):
    """时间序列数据点."""
    
    timestamp: str = Field(
        ...,
        description="时间戳，ISO 8601格式"
    )
    value: float = Field(
        ...,
        description="观测值"
    )


class PredictionConfig(BaseModel):
    """预测配置."""
    
    steps: int = Field(
        ...,
        description="预测步数",
        gt=0
    )


class PredictRequest(BaseModel):
    """预测请求."""

    data: list[TimeSeriesPoint] = Field(
        ...,
        description="历史时间序列数据"
    )
    config: PredictionConfig = Field(
        ...,
        description="预测配置"
    )
    
    def to_series(self) -> pd.Series:
        """转换为 pandas Series."""
        timestamps = pd.to_datetime([point.timestamp for point in self.data])
        values = [point.value for point in self.data]
        return pd.Series(values, index=timestamps)


class ResponseMetadata(BaseModel):
    """响应元数据."""
    
    model_uri: Optional[str] = Field(None, description="模型URI")
    prediction_steps: int = Field(..., description="预测步数")
    input_data_points: int = Field(..., description="输入数据点数")
    input_frequency: Optional[str] = Field(None, description="检测到的输入频率")
    execution_time_ms: float = Field(..., description="执行耗时（毫秒）")


class ErrorDetail(BaseModel):
    """错误详情."""
    
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[dict] = Field(None, description="详细信息")


class PredictResponse(BaseModel):
    """预测响应."""
    
    success: bool = Field(default=True, description="是否成功")
    history: Optional[list[TimeSeriesPoint]] = Field(None, description="输入的历史数据")
    prediction: Optional[list[TimeSeriesPoint]] = Field(None, description="预测的时间序列点")
    metadata: ResponseMetadata = Field(..., description="响应元数据")
    error: Optional[ErrorDetail] = Field(None, description="错误信息")
