from typing import Optional, Dict, Any
from langchain_openai import OpenAIEmbeddings
from loguru import logger
from singleton_decorator import singleton


@singleton
class EmbedManager:
    """嵌入模型管理器，支持本地和远程模型。"""
    
    # 协议前缀
    LOCAL_GPU_PREFIX = 'local-gpu:'
    LOCAL_PREFIX = 'local:'
    
    # 模型类型
    HUGGINGFACE_TYPE = 'huggingface_embedding'
    
    # 默认配置
    DEFAULT_TIMEOUT = 300

    def __init__(self):
        self._embed_instances: Dict[str, Any] = {}

    def _parse_protocol(self, protocol: str) -> tuple[str, str]:
        """解析协议字符串，返回模型类型和名称。"""
        parts = protocol.split(':')
        if len(parts) < 3:
            raise ValueError(
                f"Protocol format should be 'prefix:type:model_name', got: {protocol}")
        return parts[1], parts[2]

    def get_local_embed_instance(self, protocol: str, cache_folder: str = None) -> Optional[Any]:
        """获取本地嵌入模型实例。"""
        # 复用已存在的实例
        if protocol in self._embed_instances:
            return self._embed_instances[protocol]

        model_type, model_name = self._parse_protocol(protocol)
        
        # 确定设备类型
        device = 'cuda' if protocol.startswith(self.LOCAL_GPU_PREFIX) else 'cpu'
        logger.info(f"Creating local embed instance: {model_name} on {device}")

        if model_type != self.HUGGINGFACE_TYPE:
            logger.warning(f"Unsupported model type: {model_type}")
            return None

        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            
            self._embed_instances[protocol] = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': device},
                encode_kwargs={'normalize_embeddings': False},
                cache_folder=cache_folder
            )
            return self._embed_instances[protocol]
        except Exception as e:
            logger.error(f"Failed to create local embed instance: {e}")
            raise

    def get_embed(self, protocol: str, model_name: str = '', 
                  model_api_key: str = '', model_base_url: str = '',
                  cache_folder: str = './models') -> Any:
        """获取嵌入模型实例。"""
        if not protocol:
            raise ValueError("Protocol cannot be empty")

        # 本地模型
        if protocol.startswith(self.LOCAL_PREFIX):
            return self.get_local_embed_instance(protocol, cache_folder)
        
        # 远程模型参数校验
        if not model_name or not model_api_key:
            raise ValueError("model_name and model_api_key are required for remote embedding")

        logger.info(f"Creating remote embed instance: {model_name}")
        return OpenAIEmbeddings(
            model=model_name,
            api_key=model_api_key,
            base_url=model_base_url,
            timeout=self.DEFAULT_TIMEOUT,
        )