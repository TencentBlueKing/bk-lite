from typing import Optional

from pydantic import BaseModel, Field


class ReRankConfig(BaseModel):
    """重排序配置

    用于配置重排序模型的参数，支持本地和远程模型。
    本地模型格式：local:bce:model_name
    远程模型格式：http://example.com/rerank
    """

    model_base_url: str = Field(..., description="重排序模型的基础URL或本地协议")
    model_name: str = Field(..., description="重排序模型名称")
    api_key: str = Field(default="", description="API密钥，本地模型可为空")
    query: str = Field(..., description="查询文本")
    top_k: int = Field(..., gt=0, description="返回的前K个结果数量")
    threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="相关性分数阈值")
