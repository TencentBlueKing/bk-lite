from typing import Iterable
from loguru import logger
from graphiti_core.embedder.client import EmbedderClient
from neco.llm.embed.embed_manager import EmbedManager
from neco.core.utils.timing_decorator import timeit
from neco.llm.rag.graph_rag.graphiti.metis_embedder_config import MetisEmbedderConfig


class MetisEmbedder(EmbedderClient):
    def __init__(self, config: MetisEmbedderConfig):
        """初始化Metis嵌入器。

        Args:
            config: 嵌入器配置，包含URL、模型名称和API密钥

        Raises:
            ValueError: 当配置参数无效时
            Exception: 当嵌入器初始化失败时
        """
        if not config:
            raise ValueError("配置不能为空")

        try:
            logger.info(f"初始化Metis嵌入器，模型: {config.model_name}")
            # 修复：移除重复的config.url参数
            self.embed = EmbedManager().get_embed(
                config.url, config.model_name,
                config.api_key, config.url if config.url.startswith(
                    ('http://', 'https://')) else ''
            )
            logger.info("Metis嵌入器初始化成功")
        except Exception as e:
            logger.error(f"Metis嵌入器初始化失败: {e}")
            raise

    @timeit("metis_embed_create")
    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        """创建单个嵌入向量。

        Args:
            input_data: 输入数据，支持字符串、字符串列表或数值迭代器

        Returns:
            嵌入向量

        Raises:
            ValueError: 当输入数据无效时
            Exception: 当嵌入生成失败时
        """
        if not input_data:
            raise ValueError("输入数据不能为空")

        try:
            # 处理不同类型的输入数据
            if isinstance(input_data, str):
                logger.debug(f"生成文本嵌入，长度: {len(input_data)}")
                result = self.embed.embed_documents([input_data])
                return result[0]
            elif isinstance(input_data, list) and all(isinstance(item, str) for item in input_data):
                logger.debug(f"生成批量文本嵌入，数量: {len(input_data)}")
                result = self.embed.embed_documents(input_data)
                return result[0] if result else []
            else:
                # 处理数值迭代器类型
                logger.debug("处理数值类型输入数据")
                # 对于数值类型，直接转换为字符串处理
                if hasattr(input_data, '__iter__'):
                    str_data = str(list(input_data))
                else:
                    str_data = str(input_data)
                result = self.embed.embed_documents([str_data])
                return result[0]

        except Exception as e:
            logger.error(f"嵌入生成失败: {e}")
            raise

    @timeit("metis_embed_create_batch")
    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """批量创建嵌入向量。

        Args:
            input_data_list: 输入文本列表

        Returns:
            嵌入向量列表

        Raises:
            ValueError: 当输入数据无效时
            Exception: 当批量嵌入生成失败时
        """
        if not input_data_list:
            raise ValueError("输入数据列表不能为空")

        if not all(isinstance(item, str) for item in input_data_list):
            raise ValueError("输入数据列表必须全部为字符串类型")

        try:
            logger.debug(f"批量生成嵌入向量，数量: {len(input_data_list)}")
            result = self.embed.embed_documents(input_data_list)
            logger.debug(f"批量嵌入生成完成，向量数量: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"批量嵌入生成失败: {e}")
            raise
