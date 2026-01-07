"""Pydantic schemas for request/response validation."""

from typing import List, Optional

from pydantic import BaseModel, Field


class LogClusterRequest(BaseModel):
    """日志聚类请求."""

    logs: List[str] = Field(
        ...,
        description="日志消息列表",
        examples=[
            [
                "User login failed from IP 192.168.1.100",
                "Database connection timeout after 30 seconds",
                "User login failed from IP 10.0.0.5",
            ]
        ],
    )


class LogClusterResult(BaseModel):
    """单条日志的聚类结果."""

    log: str = Field(..., description="原始日志消息")
    cluster_id: int = Field(..., description="聚类 ID（模板 ID）")
    template: Optional[str] = Field(None, description="对应的日志模板")


class LogClusterResponse(BaseModel):
    """日志聚类响应."""

    results: List[LogClusterResult] = Field(..., description="聚类结果列表")
    num_templates: int = Field(..., description="发现的模板总数")
    model_version: str = Field(..., description="模型版本")
    source: str = Field(..., description="模型来源: local/mlflow/dummy")


# 保持原有的通用预测接口向后兼容
class PredictRequest(BaseModel):
    """预测请求（通用接口）."""

    features: dict[str, float] = Field(
        ...,
        description="特征字典,键为特征名,值为特征值",
        examples=[{"feature1": 1.0, "feature2": 2.5, "feature3": 0.8}],
    )


class PredictResponse(BaseModel):
    """预测响应（通用接口）."""

    prediction: float = Field(..., description="预测结果")
    model_version: str = Field(..., description="模型版本")
    source: str = Field(..., description="模型来源: local/mlflow/dummy")
