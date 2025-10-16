from pydantic import BaseModel, Field


class MetisRerankerConfig(BaseModel):
    """Metis重排序模型配置

    用于配置Metis重排序服务的连接参数和认证信息。
    """
    url: str = Field(..., description="重排序服务的基础URL")
    model_name: str = Field(..., description="重排序模型名称")
    api_key: str = Field(default="", description="API密钥，本地服务可为空")
