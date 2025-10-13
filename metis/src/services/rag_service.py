import time
import uuid
from datetime import datetime

from loguru import logger

from neco.llm.chunk.fixed_size_chunk import FixedSizeChunk
from neco.llm.chunk.full_chunk import FullChunk
from neco.llm.chunk.recursive_chunk import RecursiveChunk
from neco.llm.chunk.semantic_chunk import SemanticChunk
from neco.llm.embed.embed_manager import EmbedManager
from neco.llm.loader.doc_loader import DocLoader
from neco.llm.loader.excel_loader import ExcelLoader
from neco.llm.loader.markdown_loader import MarkdownLoader
from neco.llm.loader.pdf_loader import PDFLoader
from neco.llm.loader.text_loader import TextLoader
from neco.ocr.ocr_manager import OcrManager
from src.core_settings import core_settings
from neco.llm.rag.naive_rag_entity import DocumentIngestRequest
from neco.llm.loader.image_loader import ImageLoader
from neco.llm.loader.ppt_loader import PPTLoader
from neco.llm.rag.naive_rag.pgvector.pgvector_rag import PgvectorRag


class RagService:
    @classmethod
    def store_documents_to_pg(cls, chunked_docs, knowledge_base_id, embed_model_base_url,
                              embed_model_api_key, embed_model_name, metadata={}):
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
        logger.debug(
            f"存储文档到PgVector, 知识库ID: {knowledge_base_id}, 模型名称: {embed_model_name}, 分块数: {len(chunked_docs)}")

        # 自动添加创建时间
        created_time = datetime.now().isoformat()
        logger.debug(f"为文档添加创建时间: {created_time}")

        for doc in chunked_docs:
            # 添加创建时间到每个文档的元数据中
            doc.metadata['created_time'] = created_time

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

        start_time = time.time()
        rag = PgvectorRag(
            db_url=core_settings.db_uri
        )
        rag.ingest(pg_store_request)
        elapsed_time = time.time() - start_time
        logger.debug(f"PgVector存储完成, 耗时: {elapsed_time:.2f}秒")

    @classmethod
    def store_documents_to_pg(cls,
                              chunked_docs, knowledge_base_id, embed_model_base_url,
                              embed_model_api_key, embed_model_name, metadata={}):
        logger.debug(
            f"""存储文档到PostgreSQL, 知识库ID: {knowledge_base_id}, 模型名称: {embed_model_name},分块数: {len(chunked_docs)} """)

        # 自动添加创建时间
        for doc in chunked_docs:
            created_time = datetime.now().isoformat()
            doc.metadata['created_time'] = created_time

        # 应用额外的元数据
        if metadata:
            for doc in chunked_docs:
                doc.metadata.update(metadata)

        # 构建存储请求
        pgvector_store_request = DocumentIngestRequest(
            index_name=knowledge_base_id,
            docs=chunked_docs,
            embed_model_base_url=embed_model_base_url,
            embed_model_api_key=embed_model_api_key,
            embed_model_name=embed_model_name,
        )

        try:
            start_time = time.time()
            rag = PgvectorRag()
            rag.ingest(pgvector_store_request)
            elapsed_time = time.time() - start_time

            logger.debug(f"PostgreSQL存储完成, 耗时: {elapsed_time:.2f}秒")

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"PostgreSQL存储失败, 耗时: {elapsed_time:.2f}秒, 错误: {e}")
            raise

    @classmethod
    def perform_chunking(cls, docs, chunk_mode, request, is_preview, content_type):
        """
        执行文档分块并记录相关日志

        Args:
            docs: 文档列表
            chunk_mode: 分块模式
            request: HTTP请求对象
            is_preview: 是否为预览模式
            content_type: 内容类型

        Returns:
            分块后的文档列表
        """
        mode = "预览" if is_preview else "正式处理"
        logger.debug(
            f"{content_type}分块 [{mode}], 模式: {chunk_mode}, 文档数: {len(docs)}")

        chunker = RagService.get_chunker(chunk_mode, request)
        chunked_docs = chunker.chunk(docs)
        logger.debug(
            f"{content_type}分块完成, 输入文档: {len(docs)}, 输出分块: {len(chunked_docs)}")
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
        logger.debug(
            f"准备文档元数据 [{mode}], 标题: {title}, 知识ID: {knowledge_id}, 文档数: {len(docs)}")
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
            serialized_docs.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata
            })
        return serialized_docs

    @classmethod
    def process_documents(cls, docs, knowledge_title, knowledge_id=None):
        """
        处理文档，添加元数据
        """
        logger.debug(
            f"处理文档元数据，标题: {knowledge_title}, ID: {knowledge_id}, 文档数量: {len(docs)}")
        for index, doc in enumerate(docs):
            doc.metadata['knowledge_title'] = knowledge_title
            if knowledge_id:
                doc.metadata['knowledge_id'] = knowledge_id
            doc.metadata['segment_id'] = str(uuid.uuid4())
            doc.metadata['segment_number'] = str(index)
        return docs

    @classmethod
    def get_chunker(cls, chunk_mode, request=None):
        """
        根据分块模式返回相应的分块器
        """
        logger.debug(f"初始化分块器，模式: {chunk_mode}")
        if chunk_mode == 'fixed_size':
            chunk_size = int(request.form.get('chunk_size', 256))
            logger.debug(f"使用固定大小分块，大小: {chunk_size}")
            return FixedSizeChunk(chunk_size=chunk_size)

        elif chunk_mode == 'full':
            logger.debug("使用全文分块")
            return FullChunk()

        elif chunk_mode == 'recursive':
            chunk_size = int(request.form.get('chunk_size', 256))
            chunk_overlap = int(request.form.get('chunk_overlap', 128))
            logger.debug(f"使用递归分块，大小: {chunk_size}, 重叠: {chunk_overlap}")
            return RecursiveChunk(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        elif chunk_mode == 'semantic':
            semantic_chunk_model = request.form.get('semantic_chunk_model')
            semantic_chunk_model_base_url = request.form.get(
                'semantic_chunk_model_base_url')
            logger.debug(
                f"使用语义分块，模型: {semantic_chunk_model}, URL: {semantic_chunk_model_base_url}")
            semantic_chunk_model_api_key = request.form.get(
                'semantic_chunk_model_api_key')
            embeddings = EmbedManager().get_embed(protocol=semantic_chunk_model_base_url, model_name=semantic_chunk_model,
                                                  model_api_key=semantic_chunk_model_api_key,
                                                  model_base_url=semantic_chunk_model_base_url)
            return SemanticChunk(embeddings)
        else:
            error_msg = f"不支持的分块模式: {chunk_mode}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    @classmethod
    def get_file_loader(cls, file_path, file_extension, load_mode, request=None):
        """
        根据文件类型选择适当的加载器
        在内部初始化OCR，支持paddle_ocr、olm_ocr、azure_ocr
        """
        logger.debug(f"为文件 {file_path} (类型: {file_extension}) 初始化加载器")

        oct_type = request.form.get('ocr_type')
        base_url = request.form.get(
            'olm_base_url') or request.form.get('azure_base_url')
        model = request.form.get('olm_model')
        api_key = request.form.get(
            'olm_api_key') or request.form.get('azure_api_key')

        ocr = OcrManager.load_ocr(ocr_type=oct_type, model=model,
                                  base_url=base_url, api_key=api_key)

        if file_extension in ['docx', 'doc']:
            return DocLoader(file_path, ocr, load_mode)
        elif file_extension in ['pptx', 'ppt']:
            return PPTLoader(file_path, load_mode)
        elif file_extension == 'txt':
            return TextLoader(file_path, load_mode)
        elif file_extension in ['jpg', 'png', 'jpeg']:
            return ImageLoader(file_path, ocr, load_mode)
        elif file_extension == 'pdf':
            return PDFLoader(file_path, ocr, load_mode)
        elif file_extension in ['xlsx', 'xls', 'csv']:
            return ExcelLoader(file_path, load_mode)
        elif file_extension in ['md']:
            return MarkdownLoader(file_path, load_mode)
        else:
            raise ValueError(f"不支持的文件类型: {file_extension}")
