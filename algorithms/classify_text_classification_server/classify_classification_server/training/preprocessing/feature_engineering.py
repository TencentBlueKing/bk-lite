"""文本特征工程器"""
import re
from typing import List, Optional
import numpy as np
import scipy.sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from loguru import logger


class TextFeatureEngineer:
    """文本特征工程器
    
    组合两类特征：
    1. TF-IDF 文本特征（scikit-learn TfidfVectorizer）
    2. 统计特征（文本长度、分词数量、特殊字符比例、数字比例、平均词长）
    
    特征拼接：TF-IDF (稀疏矩阵) + 统计特征 (密集矩阵) -> 混合特征矩阵 (稀疏矩阵)
    """
    
    def __init__(self, config: dict):
        """初始化特征工程器
        
        Args:
            config: 特征工程配置字典
                - use_tfidf: 是否使用 TF-IDF 特征，默认 True
                - use_statistical: 是否使用统计特征，默认 True
                - tfidf: TF-IDF 配置
                    - max_features: 最大特征数，默认 5000
                    - min_df: 最小文档频率，默认 2
                    - max_df: 最大文档频率，默认 0.95
                    - ngram_range: n-gram 范围，默认 [1, 2]
                    - use_idf: 是否使用 IDF，默认 True
                    - sublinear_tf: 是否使用对数 TF，默认 True
                - statistical_features: 统计特征列表，默认全部启用
        """
        self.config = config
        self.use_tfidf = config.get("use_tfidf", True)
        self.use_statistical = config.get("use_statistical", True)
        
        # TF-IDF 配置
        tfidf_config = config.get("tfidf", {})
        self.tfidf_vectorizer = None
        
        if self.use_tfidf:
            self.tfidf_vectorizer = TfidfVectorizer(
                max_features=tfidf_config.get("max_features", 5000),
                min_df=tfidf_config.get("min_df", 2),
                max_df=tfidf_config.get("max_df", 0.95),
                ngram_range=tuple(tfidf_config.get("ngram_range", [1, 2])),
                use_idf=tfidf_config.get("use_idf", True),
                sublinear_tf=tfidf_config.get("sublinear_tf", True),
                lowercase=False,  # 已经在预处理中处理过
                token_pattern=r'(?u)\b\w+\b',  # 支持中文分词后的词语
            )
        
        # 统计特征配置
        self.statistical_features = config.get("statistical_features", [
            "text_length",
            "token_count",
            "special_char_ratio",
            "digit_ratio",
            "avg_word_length"
        ])
        
        # 保存原始文本用于统计特征提取
        self._original_texts: Optional[List[str]] = None
        
        logger.info(f"特征工程器初始化完成: use_tfidf={self.use_tfidf}, "
                   f"use_statistical={self.use_statistical}, "
                   f"tfidf_max_features={tfidf_config.get('max_features', 5000)}, "
                   f"statistical_features={len(self.statistical_features)}")
    
    def fit_transform(self, texts: List[str], original_texts: Optional[List[str]] = None) -> scipy.sparse.csr_matrix:
        """训练并转换文本为特征矩阵
        
        Args:
            texts: 预处理后的文本列表（已分词，空格连接）
            original_texts: 原始文本列表（用于统计特征提取），如果为 None 则使用 texts
            
        Returns:
            特征矩阵（稀疏矩阵格式）
        """
        if not texts:
            raise ValueError("文本列表不能为空")
        
        self._original_texts = original_texts if original_texts is not None else texts
        
        features = []
        
        # 1. TF-IDF 特征
        if self.use_tfidf and self.tfidf_vectorizer is not None:
            logger.info(f"开始训练 TF-IDF 向量化器，文本数量: {len(texts)}")
            tfidf_features = self.tfidf_vectorizer.fit_transform(texts)
            logger.info(f"TF-IDF 特征维度: {tfidf_features.shape}, "
                       f"词汇表大小: {len(self.tfidf_vectorizer.vocabulary_)}")
            features.append(tfidf_features)
        
        # 2. 统计特征
        if self.use_statistical:
            logger.info(f"提取统计特征，特征数量: {len(self.statistical_features)}")
            stat_features = self._extract_statistical_features(self._original_texts)
            # 转换为稀疏矩阵以便拼接
            stat_features_sparse = scipy.sparse.csr_matrix(stat_features)
            logger.info(f"统计特征维度: {stat_features_sparse.shape}")
            features.append(stat_features_sparse)
        
        # 3. 拼接特征
        if len(features) == 0:
            raise ValueError("至少需要启用一种特征类型（TF-IDF 或统计特征）")
        
        if len(features) == 1:
            combined_features = features[0]
        else:
            combined_features = scipy.sparse.hstack(features, format='csr')
        
        logger.info(f"特征拼接完成，最终特征维度: {combined_features.shape}")
        
        return combined_features
    
    def transform(self, texts: List[str], original_texts: Optional[List[str]] = None) -> scipy.sparse.csr_matrix:
        """使用已训练模型转换文本为特征矩阵
        
        Args:
            texts: 预处理后的文本列表（已分词，空格连接）
            original_texts: 原始文本列表（用于统计特征提取），如果为 None 则使用 texts
            
        Returns:
            特征矩阵（稀疏矩阵格式）
        """
        if not texts:
            raise ValueError("文本列表不能为空")
        
        original_texts = original_texts if original_texts is not None else texts
        
        features = []
        
        # 1. TF-IDF 特征
        if self.use_tfidf:
            if self.tfidf_vectorizer is None:
                raise ValueError("TF-IDF 向量化器未训练，请先调用 fit_transform")
            tfidf_features = self.tfidf_vectorizer.transform(texts)
            features.append(tfidf_features)
        
        # 2. 统计特征
        if self.use_statistical:
            stat_features = self._extract_statistical_features(original_texts)
            stat_features_sparse = scipy.sparse.csr_matrix(stat_features)
            features.append(stat_features_sparse)
        
        # 3. 拼接特征
        if len(features) == 1:
            combined_features = features[0]
        else:
            combined_features = scipy.sparse.hstack(features, format='csr')
        
        return combined_features
    
    def _extract_statistical_features(self, texts: List[str]) -> np.ndarray:
        """提取统计特征
        
        Args:
            texts: 原始文本列表
            
        Returns:
            统计特征矩阵 (n_samples, n_features)
        """
        features_list = []
        
        for text in texts:
            text_features = []
            
            # 1. text_length: 文本长度
            if "text_length" in self.statistical_features:
                text_features.append(len(text) if text else 0)
            
            # 2. token_count: 分词数量（空格分隔）
            if "token_count" in self.statistical_features:
                token_count = len(text.split()) if text else 0
                text_features.append(token_count)
            
            # 3. special_char_ratio: 特殊字符比例
            if "special_char_ratio" in self.statistical_features:
                if text and len(text) > 0:
                    special_chars = re.findall(r'[^\w\s]', text)
                    ratio = len(special_chars) / len(text)
                else:
                    ratio = 0.0
                text_features.append(ratio)
            
            # 4. digit_ratio: 数字字符比例
            if "digit_ratio" in self.statistical_features:
                if text and len(text) > 0:
                    digits = re.findall(r'\d', text)
                    ratio = len(digits) / len(text)
                else:
                    ratio = 0.0
                text_features.append(ratio)
            
            # 5. avg_word_length: 平均词长
            if "avg_word_length" in self.statistical_features:
                if text:
                    words = text.split()
                    avg_len = np.mean([len(word) for word in words]) if words else 0.0
                else:
                    avg_len = 0.0
                text_features.append(avg_len)
            
            features_list.append(text_features)
        
        return np.array(features_list, dtype=np.float32)
    
    def get_feature_names(self) -> List[str]:
        """获取所有特征名称
        
        Returns:
            特征名称列表
        """
        feature_names = []
        
        # TF-IDF 特征名称
        if self.use_tfidf and self.tfidf_vectorizer is not None:
            if hasattr(self.tfidf_vectorizer, 'get_feature_names_out'):
                tfidf_names = self.tfidf_vectorizer.get_feature_names_out().tolist()
            else:
                tfidf_names = self.tfidf_vectorizer.get_feature_names()
            feature_names.extend(tfidf_names)
        
        # 统计特征名称
        if self.use_statistical:
            feature_names.extend(self.statistical_features)
        
        return feature_names
    
    def get_vectorizer(self):
        """获取 TF-IDF 向量化器（用于模型保存）
        
        Returns:
            TfidfVectorizer 对象
        """
        return self.tfidf_vectorizer
    
    def get_feature_dimensions(self) -> dict:
        """获取各类特征的维度信息
        
        Returns:
            特征维度信息字典
        """
        dims = {}
        
        if self.use_tfidf and self.tfidf_vectorizer is not None:
            if hasattr(self.tfidf_vectorizer, 'vocabulary_'):
                dims['tfidf'] = len(self.tfidf_vectorizer.vocabulary_)
            else:
                dims['tfidf'] = 0
        
        if self.use_statistical:
            dims['statistical'] = len(self.statistical_features)
        
        dims['total'] = sum(dims.values())
        
        return dims
