from pydantic import BaseModel, Field


class MetisEmbedderConfig(BaseModel):
    """Metis嵌入器模型配置

    用于配置Metis嵌入服务的连接参数和认证信息。
    支持本地和远程嵌入服务。
    """
    url: str = Field(..., description="嵌入服务的基础URL")
    model_name: str = Field(..., description="嵌入模型名称")
    api_key: str = Field(default="", description="API密钥，本地服务可为空")
