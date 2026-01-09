"""Pydantic schemas for request/response validation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class LogClusterConfig(BaseModel):
    """日志聚类配置参数."""
    
    return_details: bool = Field(
        False,
        description="是否返回原始明细（默认只返回聚合视图）"
    )
    
    max_samples: int = Field(
        5,
        ge=1,
        le=20,
        description="每个模板返回的样本数量（1-20）"
    )
    
    sort_by: str = Field(
        "count",
        pattern="^(count|cluster_id)$",
        description="排序方式: count（按出现次数降序）, cluster_id（按ID升序）"
    )


class LogClusterRequest(BaseModel):
    """日志聚类请求."""

    data: List[str] = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="日志消息列表（1-10000条）",
        examples=[
            [
                "User login failed from IP 192.168.1.100",
                "Database connection timeout after 30 seconds",
                "User login failed from IP 10.0.0.5",
            ]
        ],
    )
    
    config: LogClusterConfig = Field(
        default_factory=LogClusterConfig,
        description="聚类配置参数"
    )
    
    @field_validator('data')
    @classmethod
    def validate_log_size(cls, v: List[str]) -> List[str]:
        """验证单条日志大小不超过10KB"""
        max_size = 10 * 1024  # 10KB
        for i, log in enumerate(v):
            if len(log.encode('utf-8')) > max_size:
                raise ValueError(
                    f"日志[{i}]大小超过限制: {len(log.encode('utf-8'))} bytes > {max_size} bytes"
                )
        return v


class LogClusterResult(BaseModel):
    """单条日志的聚类结果（用于可选的详细模式）."""

    log: str = Field(..., description="原始日志消息")
    cluster_id: int = Field(..., description="聚类 ID（模板 ID）")
    template: Optional[str] = Field(None, description="对应的日志模板")


# ==================== P0 优化：聚合响应格式 ====================

class TemplateGroup(BaseModel):
    """模板分组（聚合视图核心）."""
    
    cluster_id: int = Field(..., description="模板 ID")
    template: str = Field(..., description="日志模板")
    count: int = Field(..., ge=0, description="匹配此模板的日志数量")
    percentage: float = Field(..., ge=0.0, le=100.0, description="占比（%）")
    log_indices: List[int] = Field(..., description="匹配日志的原始索引位置")
    sample_logs: List[str] = Field(
        ...,
        max_length=20,
        description="代表性日志样本（最多20条）"
    )


class ClusteringSummary(BaseModel):
    """聚类摘要统计."""
    
    total_logs: int = Field(..., ge=0, description="日志总数")
    matched_logs: int = Field(..., ge=0, description="成功匹配的日志数")
    unknown_logs: int = Field(..., ge=0, description="未匹配的日志数（可能是异常）")
    num_templates: int = Field(..., ge=0, description="发现的模板总数")
    coverage_rate: float = Field(..., ge=0.0, le=1.0, description="覆盖率（成功匹配比例）")
    processing_time_ms: float = Field(..., ge=0.0, description="处理耗时（毫秒）")


class LogClusterResponseV2(BaseModel):
    """日志聚类响应（P0优化版：聚合视图）."""
    
    # 核心聚合数据
    summary: ClusteringSummary = Field(..., description="聚类摘要统计")
    template_groups: List[TemplateGroup] = Field(
        ...,
        description="按模板分组的聚合结果（按count降序或cluster_id升序）"
    )
    
    # 异常信息（P0优化：未知日志标记）
    unknown_logs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="未匹配任何模板的日志（可能是新型故障）"
    )
    
    # 元数据
    model_info: Dict[str, Any] = Field(
        ...,
        description="模型元信息（版本、来源、参数等）"
    )
    
    # 可选：原始明细（按需返回）
    details: Optional[List[LogClusterResult]] = Field(
        None,
        description="原始明细列表（仅在 return_details=true 时返回）"
    )
