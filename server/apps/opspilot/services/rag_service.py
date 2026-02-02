import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from loguru import logger

from apps.opspilot.metis.llm.chunk.fixed_size_chunk import FixedSizeChunk
from apps.opspilot.metis.llm.chunk.full_chunk import FullChunk
from apps.opspilot.metis.llm.chunk.recursive_chunk import RecursiveChunk
from apps.opspilot.metis.llm.chunk.semantic_chunk import SemanticChunk
from apps.opspilot.metis.llm.embed.embed_manager import EmbedManager
from apps.opspilot.metis.llm.loader.doc_loader import DocLoader
from apps.opspilot.metis.llm.loader.excel_loader import ExcelLoader
from apps.opspilot.metis.llm.loader.image_loader import ImageLoader
from apps.opspilot.metis.llm.loader.markdown_loader import MarkdownLoader
from apps.opspilot.metis.llm.loader.pdf_loader import PDFLoader
from apps.opspilot.metis.llm.loader.ppt_loader import PPTLoader
from apps.opspilot.metis.llm.loader.text_loader import TextLoader
from apps.opspilot.metis.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag
from apps.opspilot.metis.llm.rag.naive_rag_entity import DocumentIngestRequest
from apps.opspilot.metis.ocr.ocr_manager import OcrManager
from apps.opspilot.models import KnowledgeBase, KnowledgeDocument, LLMModel
from apps.opspilot.services.knowledge_search_service import KnowledgeSearchService


class RAGService:
    """处理RAG(检索增强生成)相关的服务"""

    @classmethod
    def format_naive_rag_kwargs(cls, kwargs: Dict[str, Any]) -> Tuple[List, Dict, Dict]:
        """
        搜索相关文档以提供上下文

        Args:
            kwargs: 包含搜索所需参数的字典

        Returns:
            naive_rag_request列表、km_request字典、doc_map字典
        """
        naive_rag_request = []
        score_threshold_map = {i["knowledge_base"]: i["score"] for i in kwargs["rag_score_threshold"]}
        base_ids = list(score_threshold_map.keys())

        # 获取知识库和文档
        knowledge_base_list = KnowledgeBase.objects.filter(id__in=base_ids)
        doc_list = list(
            KnowledgeDocument.objects.filter(knowledge_base_id__in=base_ids).values("id", "knowledge_source_type", "name", "knowledge_base_id")
        )
        doc_map = {i["id"]: i for i in doc_list}
        km_request = cls.set_km_request(knowledge_base_list, kwargs["enable_km_route"], kwargs["km_llm_model"])

        # 为每个知识库搜索相关文档
        for knowledge_base in knowledge_base_list:
            default_kwargs = cls.set_default_naive_rag_kwargs(knowledge_base, score_threshold_map)
            if knowledge_base.enable_naive_rag:
                params = dict(
                    default_kwargs,
                    **{
                        "enable_naive_rag": True,
                        "enable_qa_rag": False,
                        "enable_graph_rag": False,
                    },
                )
                naive_rag_request.append(params)
            if knowledge_base.enable_qa_rag:
                params = dict(
                    default_kwargs,
                    **{
                        "enable_naive_rag": False,
                        "enable_qa_rag": True,
                        "enable_graph_rag": False,
                    },
                )
                naive_rag_request.append(params)
            if knowledge_base.enable_graph_rag:
                graph_rag_request = KnowledgeSearchService.set_graph_rag_request(knowledge_base, {"enable_graph_rag": 1}, "")
                params = dict(
                    default_kwargs,
                    **{
                        "size": knowledge_base.rag_size,
                        "graph_rag_request": graph_rag_request,
                        "enable_naive_rag": False,
                        "enable_qa_rag": False,
                        "enable_graph_rag": True,
                    },
                )
                naive_rag_request.append(params)
        return naive_rag_request, km_request, doc_map

    @staticmethod
    def set_km_request(knowledge_base_list, enable_km_route, km_llm_model):
        """
        设置知识管理路由请求参数

        Args:
            knowledge_base_list: 知识库列表
            enable_km_route: 是否启用知识管理路由
            km_llm_model: 知识管理LLM模型ID

        Returns:
            包含路由配置的字典
        """
        km_request = {}
        if enable_km_route:
            if isinstance(km_llm_model, int) or isinstance(km_llm_model, str):
                llm_model = LLMModel.objects.get(id=km_llm_model)
            else:
                llm_model = km_llm_model
            openai_api_base = llm_model.decrypted_llm_config["openai_base_url"]
            openai_api_key = llm_model.decrypted_llm_config["openai_api_key"]
            model = llm_model.decrypted_llm_config["model"]
            km_request = {
                "km_route_llm_api_base": openai_api_base,
                "km_route_llm_api_key": openai_api_key,
                "km_route_llm_model": model,
                "km_info": [
                    {
                        "index_name": i.knowledge_index_name(),
                        "description": i.introduction,
                    }
                    for i in knowledge_base_list
                ],
            }
        return km_request

    @staticmethod
    def set_default_naive_rag_kwargs(knowledge_base, score_threshold_map):
        """
        设置默认的RAG搜索参数

        Args:
            knowledge_base: 知识库对象
            score_threshold_map: 分数阈值映射字典

        Returns:
            包含默认RAG参数的字典
        """
        embed_config = knowledge_base.embed_model.decrypted_embed_config
        embed_model_base_url = embed_config["base_url"]
        embed_model_api_key = embed_config["api_key"] or " "
        embed_model_name = embed_config.get("model", knowledge_base.embed_model.name)

        rerank_model_base_url = rerank_model_api_key = rerank_model_name = ""
        if knowledge_base.rerank_model:
            rerank_config = knowledge_base.rerank_model.decrypted_rerank_config_config
            rerank_model_base_url = rerank_config["base_url"]
            rerank_model_api_key = rerank_config["api_key"] or " "
            rerank_model_name = rerank_config.get("model", knowledge_base.rerank_model.name)

        score_threshold = score_threshold_map.get(knowledge_base.id, 0.7)
        kwargs = {
            "index_name": knowledge_base.knowledge_index_name(),
            "metadata_filter": {"enabled": "true"},
            "score_threshold": score_threshold,
            "k": knowledge_base.rag_size,
            "qa_size": knowledge_base.qa_size,
            "search_type": knowledge_base.search_type,
            "enable_rerank": knowledge_base.enable_rerank,
            "embed_model_base_url": embed_model_base_url,
            "embed_model_api_key": embed_model_api_key,
            "embed_model_name": embed_model_name,
            "rerank_model_base_url": rerank_model_base_url,
            "rerank_model_api_key": rerank_model_api_key,
            "rerank_model_name": rerank_model_name,
            "rerank_top_k": knowledge_base.rerank_top_k,
            "rag_recall_mode": knowledge_base.rag_recall_mode,
            "graph_rag_request": {},
        }
        return kwargs

    @classmethod
    def store_documents_to_pg(cls, chunked_docs, knowledge_base_id, embed_model_base_url, embed_model_api_key, embed_model_name, metadata=None):
        """
        将文档存储到PgVector

        Args:
            chunked_docs: 分块后的文档
            knowledge_base_id: 知识库ID
            embed_model_base_url: 嵌入模型基础URL
            embed_model_api_key: 嵌入模型API密钥
            embed_model_name: 嵌入模型名称
            metadata: 额外的元数据
        """
        if metadata is None:
            metadata = {}

        logger.debug(f"存储文档到PgVector, 知识库ID: {knowledge_base_id}, 模型名称: {embed_model_name}, 分块数: {len(chunked_docs)}")

        # 自动添加创建时间
        created_time = datetime.now().isoformat()
        logger.debug(f"为文档添加创建时间: {created_time}")

        for doc in chunked_docs:
            # 添加创建时间到每个文档的元数据中
            doc.metadata["created_time"] = created_time

        # 应用额外的元数据
        if metadata:
            logger.debug(f"应用额外元数据: {metadata}")
            for doc in chunked_docs:
                doc.metadata.update(metadata)

        pg_store_request = DocumentIngestRequest(
            index_name=knowledge_base_id,
            docs=chunked_docs,
            embed_model_base_url=embed_model_base_url,
            embed_model_api_key=embed_model_api_key,
            embed_model_name=embed_model_name,
        )

        try:
            start_time = time.time()
            rag = PgvectorRag()
            rag.ingest(pg_store_request)
            elapsed_time = time.time() - start_time
            logger.debug(f"PgVector存储完成, 耗时: {elapsed_time:.2f}秒")
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"PgVector存储失败, 耗时: {elapsed_time:.2f}秒, 错误: {e}")
            raise

    @classmethod
    def perform_chunking(cls, docs, chunk_mode, request_params, is_preview, content_type):
        """
        执行文档分块并记录相关日志

        Args:
            docs: 文档列表
            chunk_mode: 分块模式
            request_params: 请求参数字典
            is_preview: 是否为预览模式
            content_type: 内容类型

        Returns:
            分块后的文档列表
        """
        mode = "预览" if is_preview else "正式处理"
        logger.debug(f"{content_type}分块 [{mode}], 模式: {chunk_mode}, 文档数: {len(docs)}")

        chunker = cls.get_chunker(chunk_mode, request_params)
        chunked_docs = chunker.chunk(docs)
        logger.debug(f"{content_type}分块完成, 输入文档: {len(docs)}, 输出分块: {len(chunked_docs)}")
        return chunked_docs

    @classmethod
    def prepare_documents_metadata(cls, docs, is_preview, title, knowledge_id=None):
        """
        准备文档的元数据

        Args:
            docs: 文档列表
            is_preview: 是否为预览模式
            title: 文档标题
            knowledge_id: 知识库ID，预览模式下不需要

        Returns:
            处理后的文档列表
        """
        mode = "预览" if is_preview else "正式处理"
        logger.debug(f"准备文档元数据 [{mode}], 标题: {title}, 知识ID: {knowledge_id}, 文档数: {len(docs)}")
        if is_preview:
            return cls.process_documents(docs, title)
        else:
            return cls.process_documents(docs, title, knowledge_id)

    @classmethod
    def serialize_documents(cls, docs):
        """
        将文档序列化为JSON格式
        """
        logger.debug(f"序列化 {len(docs)} 个文档")
        serialized_docs = []
        for doc in docs:
            serialized_docs.append({"page_content": doc.page_content, "metadata": doc.metadata})
        return serialized_docs

    @classmethod
    def process_documents(cls, docs, knowledge_title, knowledge_id=None):
        """
        处理文档，添加元数据
        """
        logger.debug(f"处理文档元数据，标题: {knowledge_title}, ID: {knowledge_id}, 文档数量: {len(docs)}")
        for index, doc in enumerate(docs):
            doc.metadata["knowledge_title"] = knowledge_title
            if knowledge_id:
                doc.metadata["knowledge_id"] = knowledge_id
            doc.metadata["segment_id"] = str(uuid.uuid4())
            doc.metadata["segment_number"] = str(index)
        return docs

    @classmethod
    def get_chunker(cls, chunk_mode, request_params):
        """
        根据分块模式返回相应的分块器

        Args:
            chunk_mode: 分块模式
            request_params: 请求参数字典
        """
        logger.debug(f"初始化分块器，模式: {chunk_mode}")
        if chunk_mode == "fixed_size":
            chunk_size = int(request_params.get("chunk_size", 256))
            logger.debug(f"使用固定大小分块，大小: {chunk_size}")
            return FixedSizeChunk(chunk_size=chunk_size)

        elif chunk_mode == "full":
            logger.debug("使用全文分块")
            return FullChunk()

        elif chunk_mode == "recursive":
            chunk_size = int(request_params.get("chunk_size", 256))
            chunk_overlap = int(request_params.get("chunk_overlap", 128))
            logger.debug(f"使用递归分块，大小: {chunk_size}, 重叠: {chunk_overlap}")
            return RecursiveChunk(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        elif chunk_mode == "semantic":
            semantic_chunk_model = request_params.get("semantic_chunk_model")
            semantic_chunk_model_base_url = request_params.get("semantic_chunk_model_base_url")
            logger.debug(f"使用语义分块，模型: {semantic_chunk_model}, URL: {semantic_chunk_model_base_url}")
            semantic_chunk_model_api_key = request_params.get("semantic_chunk_model_api_key")
            embeddings = EmbedManager().get_embed(
                protocol=semantic_chunk_model_base_url,
                model_name=semantic_chunk_model,
                model_api_key=semantic_chunk_model_api_key,
                model_base_url=semantic_chunk_model_base_url,
            )
            return SemanticChunk(embeddings)
        else:
            error_msg = f"不支持的分块模式: {chunk_mode}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @classmethod
    def get_file_loader(cls, file_path, file_extension, load_mode, request_params):
        """
        根据文件类型选择适当的加载器

        Args:
            file_path: 文件路径
            file_extension: 文件扩展名
            load_mode: 加载模式
            request_params: 请求参数字典
        """
        logger.debug(f"为文件 {file_path} (类型: {file_extension}) 初始化加载器")

        ocr_type = request_params.get("ocr_type")
        base_url = request_params.get("olm_base_url") or request_params.get("azure_endpoint")
        model = request_params.get("olm_model")
        api_key = request_params.get("olm_api_key") or request_params.get("azure_api_key")

        ocr = OcrManager.load_ocr(ocr_type=ocr_type, model=model, base_url=base_url, api_key=api_key)

        if file_extension in ["docx", "doc"]:
            return DocLoader(file_path, ocr, load_mode)
        elif file_extension in ["pptx", "ppt"]:
            return PPTLoader(file_path, ocr, load_mode)
        elif file_extension == "txt":
            return TextLoader(file_path, load_mode)
        elif file_extension in ["jpg", "png", "jpeg"]:
            return ImageLoader(file_path, ocr, load_mode)
        elif file_extension == "pdf":
            return PDFLoader(file_path, ocr, load_mode)
        elif file_extension in ["xlsx", "xls", "csv"]:
            return ExcelLoader(file_path, load_mode)
        elif file_extension in ["md"]:
            return MarkdownLoader(file_path, load_mode)
        else:
            raise ValueError(f"不支持的文件类型: {file_extension}")


# 创建服务实例
rag_service = RAGService()
