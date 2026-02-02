"""Pydantic schemas for request/response validation."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class PredictionConfig(BaseModel):
    """预测配置"""
    
    top_k: int = Field(
        3,
        ge=1,
        le=10,
        description="返回Top-K个最可能的类别（1-10）"
    )
    
    return_probabilities: bool = Field(
        True,
        description="是否返回所有类别的概率分布"
    )
    
    return_feature_importance: bool = Field(
        True,
        description="是否返回特征重要性（关键词解释）"
    )
    
    max_features: int = Field(
        10,
        ge=1,
        le=50,
        description="返回最重要的N个特征（1-50）"
    )


class PredictRequest(BaseModel):
    """预测请求"""
    
    texts: list[str] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="待分类的文本列表（1-1000条）",
        examples=[
            ["用户登录失败，IP地址异常"],
            ["系统运行正常", "数据库连接超时"]
        ]
    )
    
    config: Optional[PredictionConfig] = Field(
        None,
        description="预测配置（可选）"
    )
    
    @field_validator('texts')
    @classmethod
    def validate_texts(cls, v: list[str]) -> list[str]:
        """验证文本列表"""
        MAX_BATCH_SIZE = 1000
        
        if not v:
            raise ValueError("文本列表不能为空")
        
        if len(v) > MAX_BATCH_SIZE:
            raise ValueError(
                f"批量大小超过限制: {len(v)} > {MAX_BATCH_SIZE}。"
                f"请分批调用，每批最多{MAX_BATCH_SIZE}条文本。"
            )
        
        for i, text in enumerate(v):
            if not text or not text.strip():
                raise ValueError(f"文本[{i}]不能为空或只包含空格")
        
        return v


class ClassificationLabel(BaseModel):
    """单个分类标签结果"""
    
    label: str = Field(..., description="类别名称")
    probability: float = Field(..., ge=0.0, le=1.0, description="概率")
    rank: int = Field(..., ge=1, description="排名（1表示最可能）")


class FeatureImportance(BaseModel):
    """特征重要性"""
    
    feature: str = Field(..., description="特征名称（关键词或特征）")
    importance: float = Field(..., description="重要性得分")
    contribution: str = Field(
        ...,
        description="贡献方向（positive/negative）"
    )


class TextWarning(BaseModel):
    """文本处理警告"""
    
    type: str = Field(..., description="警告类型")
    message: str = Field(..., description="警告消息")
    original_length: Optional[int] = Field(None, description="原始文本长度")
    truncated_length: Optional[int] = Field(None, description="截断后长度")


class ClassificationResult(BaseModel):
    """单条文本的分类结果"""
    
    # 索引信息
    index: int = Field(..., description="文本在输入列表中的索引位置")
    text_snippet: str = Field(..., description="文本片段（前100字符）")
    
    # 预测结果
    prediction: str = Field(..., description="预测的主类别")
    probability: float = Field(..., ge=0.0, le=1.0, description="主类别概率")
    
    # Top-K结果
    top_predictions: list[ClassificationLabel] = Field(
        ...,
        description="Top-K预测结果"
    )
    
    # 特征重要性（可选）
    feature_importance: Optional[list[FeatureImportance]] = Field(
        None,
        description="影响预测的关键特征（词语）"
    )
    
    # 文本统计
    text_length: int = Field(..., description="原始文本长度（字符数）")
    token_count: Optional[int] = Field(None, description="分词后token数量")
    
    # 警告信息
    warnings: list[TextWarning] = Field(
        default_factory=list,
        description="文本处理警告（如截断、特殊字符等）"
    )


class PredictionSummary(BaseModel):
    """批量预测汇总统计"""
    
    total_samples: int = Field(..., description="样本总数")
    
    class_distribution: dict[str, int] = Field(
        ...,
        description="预测类别分布（各类别预测数量）"
    )
    
    avg_probability: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="平均预测概率"
    )
    
    processing_time_ms: float = Field(
        ...,
        ge=0.0,
        description="总处理耗时（毫秒）"
    )
    
    warnings_count: int = Field(
        0,
        ge=0,
        description="警告总数（截断、异常等）"
    )


class ResponseMetadata(BaseModel):
    """响应元数据"""
    
    model_uri: Optional[str] = Field(None, description="模型URI")
    model_source: str = Field(..., description="模型来源（local/mlflow/dummy）")
    
    # 配置信息
    config_used: dict = Field(..., description="实际使用的配置")
    
    # 时间信息
    request_time: str = Field(..., description="请求时间（ISO格式）")
    execution_time_ms: float = Field(..., description="执行耗时（毫秒）")


class ErrorDetail(BaseModel):
    """错误详情"""
    
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: dict = Field(default_factory=dict, description="详细信息")
    failed_indices: Optional[list[int]] = Field(
        None,
        description="失败的文本索引（部分失败时）"
    )


class PredictResponse(BaseModel):
    """预测响应"""
    
    success: bool = Field(..., description="是否成功")
    
    # 核心结果
    results: Optional[list[ClassificationResult]] = Field(
        None,
        description="每条文本的分类结果"
    )
    
    # 汇总统计
    summary: Optional[PredictionSummary] = Field(
        None,
        description="批量预测汇总统计"
    )
    
    # 元数据
    metadata: ResponseMetadata = Field(..., description="响应元数据")
    
    # 错误信息
    error: Optional[ErrorDetail] = Field(
        None,
        description="错误详情（失败时）"
    )
