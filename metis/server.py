
import traceback

from sanic import Sanic
from sanic import json
from loguru import logger
from sanic.logging.default import LOGGING_CONFIG_DEFAULTS
import logging

from neco.llm.embed.embed_manager import EmbedManager
from neco.llm.rerank.rerank_manager import ReRankManager
from src.api import api
from src.core_settings import core_settings
from neco.sanic.auth.api_auth import auth
from neco.sanic.utils.config import YamlConfig
from neco.core.utils.crypto import PasswordCrypto
from neco.ocr.pp_ocr import PPOcr
from neco.llm.common.tracing import setup_llm_tracing
import os

if core_settings.enable_llm_trace:
    setup_llm_tracing(core_settings.mlflow_tracking_uri, 'metis')

# 全局变量，延迟初始化
crypto = None
users = {}


def init_auth():
    """初始化认证配置"""
    global crypto, users
    if core_settings.is_prod_mode():
        logger.info("生产模式下运行，加载鉴权配置....")
        crypto = PasswordCrypto(core_settings.secret_key)
        users = {
            "admin": crypto.encrypt(core_settings.admin_password),
        }


# 配置认证
@auth.verify_password
def verify_password(username, password) -> bool:
    if core_settings.is_debug_mode():
        return True

    # 确保认证已初始化
    if not crypto:
        init_auth()

    if username in users:
        encrypted_password = users.get(username)
        try:
            return crypto.decrypt(encrypted_password) == crypto.decrypt(password)
        except Exception as e:
            logger.error(f"请求鉴权失败: {e}, 用户名: {username}")
            return False

    return False


def bootstrap() -> Sanic:
    # 初始化认证配置
    init_auth()

    config = YamlConfig(path="config.yml")

    logging.basicConfig(level=logging.INFO)
    LOGGING_CONFIG_DEFAULTS['formatters']['generic'] = {
        'class': 'neco.sanic.log.sanic_log_formater.SanicLogFormatter',
    }
    LOGGING_CONFIG_DEFAULTS['formatters']['access'] = {
        'class': 'neco.sanic.log.sanic_log_formater.SanicAccessFormatter',
    }

    # 禁用 Sanic access 日志
    LOGGING_CONFIG_DEFAULTS['loggers']['sanic.access']['level'] = 'WARNING'

    app = Sanic("Metis", config=config, log_config=LOGGING_CONFIG_DEFAULTS)

    app.blueprint(api)

    @app.exception(Exception)
    async def global_api_exception(request, exception):
        error_traceback = traceback.format_exc()
        msg = f"全局异常捕获: {exception}, 请求路径: {request.path}, 请求参数: {request.args}\n堆栈信息: {error_traceback}"
        logger.error(msg)
        return json({}, status=500)

    # 配置启动钩子
    @app.before_server_start
    async def show_banner(app, loop):
        with open(f"src/asserts/banner.txt") as f:
            print(f.read())

        if core_settings.graphiti_enabled():
            logger.info(
                f"启动知识图谱能力, 知识图谱地址{core_settings.knowledge_graph_host}")

            from neco.llm.rag.graph_rag.graphiti.graphiti_rag import GraphitiRAG
            rag = GraphitiRAG(
                core_settings.knowledge_graph_host, core_settings.knowledge_graph_username,
                core_settings.knowledge_graph_password, core_settings.knowledge_graph_port,
                core_settings.knowledge_graph_database
            )
            await rag.setup_graph()
        else:
            logger.info("未配置 知识图谱 地址，跳过知识图谱能力的启动......")

    @app.command
    async def download_models():
        logger.info("download HuggingFace Embed Models")
        EmbedManager().get_embed('local:huggingface_embedding:BAAI/bge-small-zh-v1.5')
        EmbedManager().get_embed('local:huggingface_embedding:maidalun1020/bce-embedding-base_v1')

        logger.info("download BCE ReRank Models")
        ReRankManager.get_local_rerank_instance(
            'local:bce:maidalun1020/bce-reranker-base_v1')

        logger.info("download PaddleOCR")
        PPOcr()

        logger.info('download tiktoken')
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        encoding = tiktoken.get_encoding("o200k_base")
        encoding.encode('Metis')
    return app
