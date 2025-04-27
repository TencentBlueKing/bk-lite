import os

from langchain_openai import OpenAIEmbeddings
from loguru import logger

from src.embed.embed_builder import EmbedBuilder


def test_fast_embed():
    embed = EmbedBuilder.get_embed("local:text_embedding:BAAI/bge-small-zh-v1.5")
    result = embed.embed([
        "你好"
    ])
    logger.info(list(result))


def test_vllm_embed():
    client = OpenAIEmbeddings(
        model=os.getenv('TEST_BCE_EMBED_MODEL'),
        api_key=os.getenv('TEST_INFERENCE_TOKEN'),
        base_url=os.getenv('TEST_INFERENCE_BASE_URL'),
    )
    responses = client.embed_documents([
        "介绍"
    ])

    logger.info(responses)
