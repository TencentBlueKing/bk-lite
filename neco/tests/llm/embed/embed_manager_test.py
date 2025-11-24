from neco.llm.embed.embed_manager import EmbedManager
import os


def test_remote_embed():
    rs = EmbedManager().get_embed(
        protocol="openai",
        model_api_key=os.getenv('TEST_LLM_API_KEY'),
        model_name=os.getenv('TEST_EMBED_MODEL'),
        model_base_url=os.getenv('TEST_LLM_API_URL'),
    ).embed_documents(['测试一下嵌入模型'])
    print(rs)
