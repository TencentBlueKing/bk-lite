import os
import torch
import numpy as np
from tqdm import tqdm
from typing import List, Dict, Tuple, Type, Union, Optional, Any
from copy import deepcopy
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from loguru import logger


# 常量定义
DEFAULT_MODEL_NAME = 'maidalun1020/bce-reranker-base_v1'
DEFAULT_BATCH_SIZE = 256
DEFAULT_MAX_LENGTH = 512
DEFAULT_OVERLAP_TOKENS = 80
MAX_PASSAGE_LENGTH = 128000  # 最大文档长度限制
MIN_QUERY_LENGTH = 1
MIN_PASSAGE_LENGTH = 1
MAX_QUERY_TOKENS = 400  # 查询最大token数


class BCEReRankConfig:
    """BCE重排序模型配置"""

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_MODEL_NAME,
        use_fp16: bool = False,
        device: Optional[str] = None,
        cache_dir: Optional[str] = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
        **kwargs
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.use_fp16 = use_fp16
        self.device = device
        self.cache_dir = cache_dir or os.getenv(
            'BCE_MODEL_CACHE_DIR', './models')
        self.max_length = max_length
        self.overlap_tokens = overlap_tokens
        self.kwargs = kwargs


class BCEReRank:
    """BCE重排序模型实现

    用于对文档进行重排序，提升检索结果的相关性。
    支持GPU加速和批量处理。
    """

    def __init__(
        self,
        model_name_or_path: str = DEFAULT_MODEL_NAME,
        use_fp16: bool = False,
        device: Optional[str] = None,
        **kwargs
    ) -> None:
        """初始化BCE重排序模型

        Args:
            model_name_or_path: 模型名称或路径
            use_fp16: 是否使用半精度浮点数
            device: 指定设备，如'cpu', 'cuda', 'cuda:0'等
            **kwargs: 其他配置参数

        Raises:
            ValueError: 设备配置错误
            RuntimeError: 模型加载失败
        """
        logger.info(f"正在初始化BCE重排序模型: {model_name_or_path}")

        self.config = BCEReRankConfig(
            model_name_or_path=model_name_or_path,
            use_fp16=use_fp16,
            device=device,
            **kwargs
        )

        try:
            self._load_model()
            self._setup_device()
            self._configure_model()

            logger.info(
                f"BCE重排序模型初始化完成 - "
                f"设备: {self.device}, GPU数量: {self.num_gpus}, "
                f"FP16: {use_fp16}, 模型: {model_name_or_path}"
            )
        except Exception as e:
            logger.error(f"BCE重排序模型初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"模型初始化失败: {e}") from e

    def _load_model(self) -> None:
        """加载tokenizer和模型"""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name_or_path,
                cache_dir=self.config.cache_dir,
                **self.config.kwargs
            )
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.config.model_name_or_path,
                cache_dir=self.config.cache_dir,
                **self.config.kwargs
            )
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

    def _setup_device(self) -> None:
        """设置计算设备"""
        num_gpus = torch.cuda.device_count()

        if self.config.device is None:
            self.device = "cuda" if num_gpus > 0 else "cpu"
        else:
            device_str = self.config.device
            if device_str.isdigit():
                self.device = f'cuda:{int(device_str)}'
            else:
                self.device = device_str

        # 验证设备有效性
        if self.device not in ["cpu", "cuda"] and not self.device.startswith('cuda:'):
            raise ValueError(
                f"无效设备配置: {self.device}. 支持的设备: 'cpu', 'cuda', 'cuda:0'等")

        # 设置GPU数量
        if self.device == "cpu":
            self.num_gpus = 0
        elif self.device.startswith('cuda:') and num_gpus > 0:
            self.num_gpus = 1
        elif self.device == "cuda":
            self.num_gpus = num_gpus
        else:
            logger.warning(f"设备 {self.device} 不可用，回退到CPU")
            self.device = "cpu"
            self.num_gpus = 0

    def _configure_model(self) -> None:
        """配置模型"""
        if self.config.use_fp16:
            self.model.half()

        self.model.eval()
        self.model = self.model.to(self.device)

        if self.num_gpus > 1:
            self.model = torch.nn.DataParallel(self.model)

    def compute_score(
        self,
        sentence_pairs: Union[List[Tuple[str, str]], Tuple[str, str]],
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_length: int = DEFAULT_MAX_LENGTH,
        enable_tqdm: bool = True,
        **kwargs
    ) -> Union[float, List[float]]:
        """计算句子对的相似度分数

        Args:
            sentence_pairs: 句子对列表或单个句子对
            batch_size: 批处理大小
            max_length: 最大序列长度
            enable_tqdm: 是否显示进度条
            **kwargs: 其他参数

        Returns:
            相似度分数或分数列表

        Raises:
            ValueError: 输入格式错误
        """
        # 输入验证
        if not sentence_pairs:
            raise ValueError("sentence_pairs不能为空")

        if self.num_gpus > 1:
            batch_size = batch_size * self.num_gpus

        # 标准化输入格式
        if not isinstance(sentence_pairs, list):
            sentence_pairs = [sentence_pairs]

        if len(sentence_pairs) > 0 and isinstance(sentence_pairs[0], str):
            sentence_pairs = [sentence_pairs]

        logger.debug(
            f"开始计算相似度分数 - 句子对数量: {len(sentence_pairs)}, 批大小: {batch_size}")

        try:
            with torch.no_grad():
                scores_collection = []
                total_batches = (len(sentence_pairs) +
                                 batch_size - 1) // batch_size

                for sentence_id in tqdm(
                    range(0, len(sentence_pairs), batch_size),
                    desc='计算相似度分数',
                    disable=not enable_tqdm,
                    total=total_batches
                ):
                    sentence_pairs_batch = sentence_pairs[sentence_id:sentence_id + batch_size]

                    inputs = self.tokenizer(
                        sentence_pairs_batch,
                        padding=True,
                        truncation=True,
                        max_length=max_length,
                        return_tensors="pt"
                    )

                    inputs_on_device = {k: v.to(self.device)
                                        for k, v in inputs.items()}
                    scores = self.model(
                        **inputs_on_device, return_dict=True).logits.view(-1).float()
                    scores = torch.sigmoid(scores)
                    scores_collection.extend(scores.cpu().numpy().tolist())

            logger.debug(f"相似度分数计算完成 - 共处理 {len(scores_collection)} 个句子对")

            if len(scores_collection) == 1:
                return scores_collection[0]
            return scores_collection

        except Exception as e:
            logger.error(f"计算相似度分数失败: {e}", exc_info=True)
            raise

    def rerank(
        self,
        query: str,
        passages: List[str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        **kwargs
    ) -> Dict[str, Any]:
        """对文档进行重排序

        Args:
            query: 查询字符串
            passages: 待重排序的文档列表
            batch_size: 批处理大小
            **kwargs: 其他参数

        Returns:
            包含重排序结果的字典，包含以下键：
            - rerank_passages: 重排序后的文档列表
            - rerank_scores: 对应的相关性分数列表
            - rerank_ids: 重排序后的原始索引列表

        Raises:
            ValueError: 输入参数无效
        """
        logger.debug(
            f"开始重排序 - 查询长度: {len(query) if query else 0}, 文档数量: {len(passages)}")

        # 输入验证和预处理
        if not self._validate_rerank_inputs(query, passages):
            return {'rerank_passages': [], 'rerank_scores': [], 'rerank_ids': []}

        # 清理和截断文档
        cleaned_passages = self._clean_passages(passages)
        if not cleaned_passages:
            logger.warning("清理后无有效文档")
            return {'rerank_passages': [], 'rerank_scores': [], 'rerank_ids': []}

        try:
            # 预处理tokenization
            sentence_pairs, sentence_pairs_pids = self._preprocess_for_tokenization(
                query, cleaned_passages
            )

            # 批量推理
            scores = self._batch_inference(sentence_pairs, batch_size)

            # 合并分数和排序
            result = self._merge_and_sort_results(
                cleaned_passages, sentence_pairs_pids, scores)

            logger.debug(
                f"重排序完成 - 输入文档: {len(passages)}, "
                f"输出文档: {len(result['rerank_passages'])}"
            )

            return result

        except Exception as e:
            logger.error(f"重排序处理失败: {e}", exc_info=True)
            return {'rerank_passages': [], 'rerank_scores': [], 'rerank_ids': []}

    def _validate_rerank_inputs(self, query: str, passages: List[str]) -> bool:
        """验证重排序输入参数"""
        if not query or len(query.strip()) < MIN_QUERY_LENGTH:
            logger.warning("查询为空或过短")
            return False

        if not passages:
            logger.warning("文档列表为空")
            return False

        return True

    def _clean_passages(self, passages: List[str]) -> List[str]:
        """清理和验证文档列表"""
        cleaned = []
        for passage in passages:
            if isinstance(passage, str) and MIN_PASSAGE_LENGTH <= len(passage.strip()):
                # 截断过长的文档
                truncated = passage[:MAX_PASSAGE_LENGTH]
                cleaned.append(truncated)

        return cleaned

    def _preprocess_for_tokenization(
        self,
        query: str,
        passages: List[str]
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """预处理tokenization"""
        return self.reranker_tokenize_preproc(
            query,
            passages,
            tokenizer=self.tokenizer,
            max_length=self.config.max_length,
            overlap_tokens=self.config.overlap_tokens,
        )

    def _batch_inference(self, sentence_pairs: List[Dict[str, Any]], batch_size: int) -> List[float]:
        """批量推理"""
        if self.num_gpus > 1:
            batch_size = batch_size * self.num_gpus

        tot_scores = []
        total_batches = (len(sentence_pairs) + batch_size - 1) // batch_size

        with torch.no_grad():
            for k in tqdm(
                range(0, len(sentence_pairs), batch_size),
                desc='重排序推理',
                total=total_batches
            ):
                batch = self.tokenizer.pad(
                    sentence_pairs[k:k + batch_size],
                    padding=True,
                    max_length=None,
                    pad_to_multiple_of=None,
                    return_tensors="pt"
                )
                batch_on_device = {k: v.to(self.device)
                                   for k, v in batch.items()}
                scores = self.model(**batch_on_device,
                                    return_dict=True).logits.view(-1).float()
                scores = torch.sigmoid(scores)
                tot_scores.extend(scores.cpu().numpy().tolist())

        return tot_scores

    def _merge_and_sort_results(
        self,
        passages: List[str],
        sentence_pairs_pids: List[int],
        scores: List[float]
    ) -> Dict[str, Any]:
        """合并分数并排序结果"""
        # 初始化每个文档的最大分数
        merge_scores = [0.0 for _ in range(len(passages))]

        # 对于每个文档片段，取最高分数
        for pid, score in zip(sentence_pairs_pids, scores):
            if 0 <= pid < len(merge_scores):
                merge_scores[pid] = max(merge_scores[pid], score)

        # 按分数降序排序
        merge_scores_argsort = np.argsort(merge_scores)[::-1]

        sorted_passages = []
        sorted_scores = []

        for mid in merge_scores_argsort:
            sorted_scores.append(merge_scores[mid])
            sorted_passages.append(passages[mid])

        return {
            'rerank_passages': sorted_passages,
            'rerank_scores': sorted_scores,
            'rerank_ids': merge_scores_argsort.tolist()
        }

    def reranker_tokenize_preproc(
        self,
        query: str,
        passages: List[str],
        tokenizer=None,
        max_length: int = DEFAULT_MAX_LENGTH,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """预处理tokenization

        将查询和文档进行tokenization预处理，支持长文档的滑动窗口切分。

        Args:
            query: 查询字符串
            passages: 文档列表
            tokenizer: tokenizer实例
            max_length: 最大序列长度
            overlap_tokens: 滑动窗口重叠token数

        Returns:
            Tuple包含：
            - 处理后的输入对列表
            - 对应的文档ID列表

        Raises:
            AssertionError: tokenizer为None
            ValueError: 查询过长
        """
        if tokenizer is None:
            raise ValueError("tokenizer不能为None")

        logger.debug(
            f"开始tokenization预处理 - 查询长度: {len(query)}, 文档数: {len(passages)}")

        try:
            sep_id = tokenizer.sep_token_id

            # 对查询进行tokenization
            query_inputs = tokenizer.encode_plus(
                query, truncation=False, padding=False)
            query_token_length = len(query_inputs['input_ids'])

            # 计算文档可用的最大token长度（减去查询tokens和分隔符）
            max_passage_tokens = max_length - query_token_length - 2

            if max_passage_tokens <= 100:
                raise ValueError(
                    f"查询过长({query_token_length} tokens)，"
                    f"请确保查询长度不超过{MAX_QUERY_TOKENS} tokens"
                )

            # 计算实际的重叠token数（不超过文档长度的1/4）
            effective_overlap = min(overlap_tokens, max_passage_tokens // 4)

            res_merge_inputs = []
            res_merge_inputs_pids = []

            for pid, passage in enumerate(passages):
                passage_inputs = tokenizer.encode_plus(
                    passage,
                    truncation=False,
                    padding=False,
                    add_special_tokens=False
                )
                passage_token_length = len(passage_inputs['input_ids'])

                if passage_token_length <= max_passage_tokens:
                    # 文档较短，直接处理
                    merged_inputs = self._merge_query_passage(
                        query_inputs, passage_inputs, sep_id)
                    res_merge_inputs.append(merged_inputs)
                    res_merge_inputs_pids.append(pid)
                else:
                    # 文档较长，使用滑动窗口
                    chunks = self._split_passage_with_sliding_window(
                        passage_inputs, max_passage_tokens, effective_overlap
                    )

                    for chunk in chunks:
                        merged_inputs = self._merge_query_passage(
                            query_inputs, chunk, sep_id)
                        res_merge_inputs.append(merged_inputs)
                        res_merge_inputs_pids.append(pid)

            logger.debug(
                f"tokenization预处理完成 - 生成输入对数: {len(res_merge_inputs)}, "
                f"文档ID数: {len(res_merge_inputs_pids)}"
            )

            return res_merge_inputs, res_merge_inputs_pids

        except Exception as e:
            logger.error(f"tokenization预处理失败: {e}", exc_info=True)
            raise

    def _merge_query_passage(
        self,
        query_inputs: Dict[str, Any],
        passage_inputs: Dict[str, Any],
        sep_id: int
    ) -> Dict[str, Any]:
        """合并查询和文档的token输入"""
        merged = deepcopy(query_inputs)

        # 构建: [CLS] query [SEP] passage [SEP]
        merged['input_ids'].append(sep_id)
        merged['input_ids'].extend(passage_inputs['input_ids'])
        merged['input_ids'].append(sep_id)

        # 扩展attention_mask
        merged['attention_mask'].append(1)  # 为第一个SEP
        merged['attention_mask'].extend(passage_inputs['attention_mask'])
        merged['attention_mask'].append(1)  # 为第二个SEP

        # 如果存在token_type_ids，为文档部分设置为1
        if 'token_type_ids' in merged:
            token_type_ids = [
                1] * (len(passage_inputs['input_ids']) + 2)  # +2 for SEPs
            merged['token_type_ids'].extend(token_type_ids)

        return merged

    def _split_passage_with_sliding_window(
        self,
        passage_inputs: Dict[str, Any],
        max_tokens: int,
        overlap_tokens: int
    ) -> List[Dict[str, Any]]:
        """使用滑动窗口分割长文档"""
        chunks = []
        passage_length = len(passage_inputs['input_ids'])
        start_idx = 0

        while start_idx < passage_length:
            end_idx = min(start_idx + max_tokens, passage_length)

            # 创建当前片段
            chunk = {k: v[start_idx:end_idx]
                     for k, v in passage_inputs.items()}
            chunks.append(chunk)

            # 计算下一个窗口的起始位置
            if end_idx >= passage_length:
                break
            start_idx = end_idx - overlap_tokens

        return chunks
