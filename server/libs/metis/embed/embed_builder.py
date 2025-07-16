from langchain_openai import OpenAIEmbeddings
import logging
logger = logging.getLogger(__name__)


class EmbedBuilder:
    _embed_instances = {}

    @classmethod
    def get_embed_instance(cls, protocol: str):
        if cls._embed_instances.get(protocol, None) is not None:
            return cls._embed_instances[protocol]

        model_type = protocol.split(':')[1]
        model_name = protocol.split(':')[2]

        if model_type == 'huggingface_embedding':
            from langchain_huggingface import HuggingFaceEmbeddings

            cls._embed_instances[protocol] = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': False},
                cache_folder="./models"
            )
            return cls._embed_instances[protocol]

        return None

    @staticmethod
    def get_embed(protocol: str, model_name: str = '', model_api_key: str = '', model_base_url: str = ''):
        if protocol.startswith('local:'):
            if EmbedBuilder._embed_instances.get(protocol, None) is not None:
                logger.info(f"使用缓存的本地Embed模型: {protocol}")
            else:
                logger.info(f"加载本地Embed模型: {protocol}")
            return EmbedBuilder.get_embed_instance(protocol)
        else:
            # 为远程模型创建缓存键
            cache_key = f"remote:{model_name}:{model_api_key}:{model_base_url}"

            if EmbedBuilder._embed_instances.get(cache_key, None) is None:
                logger.info(f"加载远程Embed模型: {model_name}")
                EmbedBuilder._embed_instances[cache_key] = OpenAIEmbeddings(
                    model=model_name,
                    api_key=model_api_key,
                    base_url=model_base_url,
                )
            else:
                logger.info(f"使用缓存的远程Embed模型: {model_name}")

            return EmbedBuilder._embed_instances[cache_key]
