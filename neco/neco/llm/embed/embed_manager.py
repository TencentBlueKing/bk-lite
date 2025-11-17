from typing import Any
from langchain_openai import OpenAIEmbeddings
from loguru import logger
from singleton_decorator import singleton


@singleton
class EmbedManager:
    """嵌入模型管理器，支持远程模型。"""

    # 默认配置
    DEFAULT_TIMEOUT = 300

    def get_embed(self, protocol: str, model_name: str = '',
                  model_api_key: str = '', model_base_url: str = '',
                  cache_folder: str = './models') -> Any:
        """获取嵌入模型实例。"""
        if not protocol:
            raise ValueError("Protocol cannot be empty")

        # 远程模型参数校验
        if not model_name or not model_api_key:
            raise ValueError(
                "model_name and model_api_key are required for remote embedding")

        logger.info(f"Creating remote embed instance: {model_name}")
        return OpenAIEmbeddings(
            model=model_name,
            api_key=model_api_key,
            base_url=model_base_url,
            timeout=self.DEFAULT_TIMEOUT,
            check_embedding_ctx_length=False,  # 禁用 token 长度检查,直接发送原始文本
        )
