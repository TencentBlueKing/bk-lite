"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """预测请求."""

    features: dict[str, float] = Field(
        ...,
        description="特征字典,键为特征名,值为特征值",
        examples=[{"feature1": 1.0, "feature2": 2.5, "feature3": 0.8}],
    )


class PredictResponse(BaseModel):
    """预测响应."""

    prediction: float = Field(..., description="预测结果")
    model_version: str = Field(..., description="模型版本")
    source: str = Field(..., description="模型来源: local/mlflow/dummy")
