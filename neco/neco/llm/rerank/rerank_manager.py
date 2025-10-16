from typing import List, Optional
import time
import threading

import requests
from langchain_core.documents import Document
from loguru import logger

from neco.llm.rerank.rerank_config import ReRankConfig


class ReRankManager:
    _rerank_instance = {}
    _instance_lock = threading.Lock()

    # 配置常量
    DEFAULT_REMOTE_TIMEOUT = 10  # 远程调用超时时间（秒）
    MAX_RETRY_ATTEMPTS = 3  # 最大重试次数
    RETRY_DELAY_BASE = 1  # 重试延迟基数（秒）

    @classmethod
    def get_local_rerank_instance(cls, protocol: str):
        """
            local:bce:maidalun1020/bce-reranker-base_v1
        """
        if cls._rerank_instance.get(protocol, None) is None:
            with cls._instance_lock:
                # 双重检查锁定模式
                if cls._rerank_instance.get(protocol, None) is None:
                    model_type = protocol.split(':')[1]
                    model_name = protocol.split(':')[2]

                    if model_type == 'bce':
                        from neco.llm.rerank.bce_rerank import BCEReRank
                        cls._rerank_instance[protocol] = BCEReRank(
                            model_name_or_path=model_name)
                        logger.info(f"成功初始化本地重排序模型: {protocol}")
                    else:
                        logger.error(f"不支持的本地重排序模型类型: {model_type}")
                        return None

        return cls._rerank_instance[protocol]

    @staticmethod
    def rerank_documents(
            rerank_model_base_url: str,
            rerank_model_name: str,
            rerank_model_api_key: str,
            search_query: str,
            search_result: List[Document],
            rerank_top_k: int,
            threshold: Optional[float] = None
    ) -> List[Document]:
        """
        统一的文档重排序处理方法

        Args:
            rerank_model_base_url: 重排序模型的基础URL
            rerank_model_name: 重排序模型名称
            rerank_model_api_key: 重排序模型API密钥
            search_query: 搜索查询
            search_result: 待重排序的文档列表
            rerank_top_k: 返回的前K个文档
            threshold: 阈值过滤（可选，会除以10进行标准化）

        Returns:
            重排序并过滤后的文档列表
        """
        config = ReRankConfig(
            model_base_url=rerank_model_base_url,
            model_name=rerank_model_name,
            api_key=rerank_model_api_key,
            query=search_query,
            top_k=rerank_top_k,
            threshold=threshold
        )

        return ReRankManager.rerank_documents_with_config(config, search_result)

    @staticmethod
    def rerank_documents_with_config(config: ReRankConfig, search_result: List[Document]) -> List[Document]:
        """
        使用配置对象进行文档重排序

        Args:
            config: 重排序配置
            search_result: 待重排序的文档列表

        Returns:
            重排序并过滤后的文档列表
        """
        if not search_result:
            return search_result

        # 执行重排序
        reranked_docs = []
        if config.model_base_url.startswith('local:'):
            logger.info(f"使用本地ReRank模型进行重排序: {config.model_base_url}")
            reranked_docs = ReRankManager._handle_local_rerank(
                config, search_result)
        else:
            logger.info(f"使用远程ReRank模型进行重排序: {config.model_base_url}")
            reranked_docs = ReRankManager._handle_remote_rerank(
                config, search_result)

        # 应用阈值过滤（如果提供了阈值）
        if config.threshold is not None and config.threshold > 0:
            return ReRankManager._filter_by_threshold(reranked_docs, config.threshold)

        return reranked_docs

    @staticmethod
    def _filter_by_threshold(docs: List[Document], threshold: float) -> List[Document]:
        """
        根据阈值过滤文档

        Args:
            docs: 待过滤的文档列表
            threshold: 阈值（会除以10进行标准化）

        Returns:
            过滤后的文档列表
        """
        if not docs or threshold <= 0:
            return docs

        normalized_threshold = threshold / 10
        filtered_docs = []

        for doc in docs:
            # 优先使用 relevance_score，其次使用 _score
            score = doc.metadata.get(
                'relevance_score', doc.metadata.get('_score', 0))
            if score >= normalized_threshold:
                filtered_docs.append(doc)

        logger.info(
            f"阈值过滤: 原始文档数={len(docs)}, 过滤后文档数={len(filtered_docs)}, 阈值={normalized_threshold}")
        return filtered_docs

    @staticmethod
    def _handle_local_rerank(
            config: ReRankConfig,
            search_result: List[Document]
    ) -> List[Document]:
        """处理本地重排序模型"""
        try:
            # 提取文档内容
            passages = [doc.page_content for doc in search_result]

            # 获取重排序实例并执行重排序
            rerank_instance = ReRankManager.get_local_rerank_instance(
                config.model_base_url)
            if rerank_instance is None:
                logger.error(f"无法获取本地重排序实例: {config.model_base_url}")
                return search_result

            local_rerank_result = rerank_instance.rerank(
                config.query, passages)
            logger.info(
                f"本地重排序完成: 处理文档数={len(passages)}, 查询='{config.query[:50]}...' if len(config.query) > 50 else config.query")

            top_k_search_result = []
            top_rerank_ids = local_rerank_result['rerank_ids'][:config.top_k]
            rerank_scores = local_rerank_result['rerank_scores']

            for i in top_rerank_ids:
                if 0 <= i < len(search_result):
                    doc = search_result[i]
                    if hasattr(doc, 'metadata'):
                        # 设置相关性分数
                        if 0 <= i < len(rerank_scores):
                            doc.metadata['relevance_score'] = rerank_scores[i]
                        else:
                            doc.metadata['relevance_score'] = 0.0
                    top_k_search_result.append(doc)
                else:
                    logger.warning(f"无效的重排序索引 {i}，跳过")

            logger.info(
                f"本地重排序结果: 原始文档数={len(search_result)}, 重排序后文档数={len(top_k_search_result)}")
            return top_k_search_result

        except Exception as e:
            logger.error(f"本地重排序处理失败: {e}, 模型协议={config.model_base_url}")
            return search_result

    @staticmethod
    def _handle_remote_rerank(
            config: ReRankConfig,
            search_result: List[Document]
    ) -> List[Document]:
        """处理远程重排序模型"""
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}"
        }

        rerank_content = [doc.page_content for doc in search_result]
        data = {
            "model": config.model_name,
            "query": config.query,
            "documents": rerank_content,
        }

        # 带重试的远程调用
        for attempt in range(ReRankManager.MAX_RETRY_ATTEMPTS):
            try:
                logger.info(
                    f"远程重排序调用尝试 {attempt + 1}/{ReRankManager.MAX_RETRY_ATTEMPTS}: {config.model_base_url}")
                response = requests.post(
                    config.model_base_url,
                    headers=headers,
                    json=data,
                    timeout=ReRankManager.DEFAULT_REMOTE_TIMEOUT
                )
                response.raise_for_status()
                rerank_api_result = response.json()

                if 'results' not in rerank_api_result:
                    logger.error(f"远程ReRank API响应格式错误: {rerank_api_result}")
                    return search_result

                rerank_result_items = rerank_api_result['results']

                # 筛选有效的重排序结果项
                valid_rerank_items = [
                    item for item in rerank_result_items
                    if 'relevance_score' in item and 'index' in item
                ]

                # 按相关性分数排序
                sorted_rerank_items = sorted(
                    valid_rerank_items, key=lambda x: x['relevance_score'], reverse=True
                )

                top_k_search_result = []
                for item in sorted_rerank_items[:config.top_k]:
                    original_index = item['index']
                    if 0 <= original_index < len(search_result):
                        doc = search_result[original_index]
                        if hasattr(doc, 'metadata'):
                            doc.metadata['relevance_score'] = item['relevance_score']
                        top_k_search_result.append(doc)
                    else:
                        logger.warning(f"无效的原始索引 {original_index}，跳过")

                logger.info(
                    f"远程重排序成功: 原始文档数={len(search_result)}, 重排序后文档数={len(top_k_search_result)}")
                return top_k_search_result

            except requests.exceptions.Timeout as e:
                logger.warning(
                    f"远程ReRank API超时 (尝试 {attempt + 1}/{ReRankManager.MAX_RETRY_ATTEMPTS}): {e}")
                if attempt < ReRankManager.MAX_RETRY_ATTEMPTS - 1:
                    delay = ReRankManager.RETRY_DELAY_BASE * \
                        (2 ** attempt)  # 指数退避
                    logger.info(f"等待 {delay} 秒后重试...")
                    time.sleep(delay)
                else:
                    logger.error(f"远程ReRank API调用最终失败，返回原始结果")
                    return search_result
            except requests.exceptions.RequestException as e:
                logger.error(
                    f"远程ReRank API请求失败 (尝试 {attempt + 1}/{ReRankManager.MAX_RETRY_ATTEMPTS}): {e}")
                if attempt < ReRankManager.MAX_RETRY_ATTEMPTS - 1:
                    delay = ReRankManager.RETRY_DELAY_BASE * \
                        (2 ** attempt)  # 指数退避
                    logger.info(f"等待 {delay} 秒后重试...")
                    time.sleep(delay)
                else:
                    logger.error(f"远程ReRank API调用最终失败，返回原始结果")
                    return search_result
            except (KeyError, TypeError) as e:
                logger.error(f"处理远程ReRank API响应时出错: {e}")
                return search_result
            except Exception as e:
                logger.error(f"远程重排序处理出现未知错误: {e}")
                return search_result
