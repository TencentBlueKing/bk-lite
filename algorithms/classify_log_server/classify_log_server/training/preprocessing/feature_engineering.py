"""
日志聚类特征工程

专为日志聚类设计的完整特征提取器。
支持多种算法类型：
- 基于模板的方法（Spell/Drain）：主要使用文本特征
- 基于深度学习的方法（LogBERT/DeepLog）：需要完整特征工程

核心特征类型：
1. 文本统计特征 - 长度、token数、数字/特殊字符比例
2. 时间特征 - 周期性模式、时间间隔
3. 日志级别特征 - ERROR/WARN/INFO权重
4. 频率特征 - 日志出现频率、罕见度
5. 序列特征 - 前后文关系
6. 语义特征 - TF-IDF/词嵌入（可选）
"""

from typing import List, Optional, Dict, Any, Tuple
from collections import Counter
import re

import pandas as pd
import numpy as np
from feature_engine.datetime import DatetimeFeatures
from loguru import logger


class LogFeatureEngineer:
    """
    日志聚类特征工程器
    
    完整的特征提取流程：
    1. 文本统计特征 - 捕捉日志结构特征
    2. 时间特征 - 捕捉时间模式（周期性、突发性）
    3. 日志级别特征 - 捕捉严重程度
    4. 频率特征 - 捕捉罕见/常见模式
    5. 序列特征 - 捕捉日志前后关系
    6. 语义特征 - 捕捉文本语义（可选）
    
    使用示例：
        config = {
            "text_features": {"enable": True},
            "time_features": {"enable": True},
            "level_features": {"enable": True},
            "frequency_features": {"enable": True},
            "sequence_features": {"enable": False},  # 需要序列数据
            "semantic_features": {"enable": False}   # 计算密集型
        }
        engineer = LogFeatureEngineer(config)
        features = engineer.fit_transform(df)
    
    注意：
    - Spell/Drain 等基于模板的方法通常不需要启用特征工程
    - LogBERT/DeepLog 等深度学习方法建议启用所有特征
    - 通过配置灵活控制特征类型
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化特征工程器

        Args:
            config: 特征工程配置字典
                {
                    "text_features": {
                        "enable": True,
                        "features": ["length", "token_count", "digit_ratio", ...]
                    },
                    "time_features": {
                        "enable": True,
                        "datetime_column": "timestamp",
                        "cyclical_features": ["hour", "day_of_week"]
                    },
                    "level_features": {
                        "enable": True,
                        "level_column": "level",
                        "levels": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
                    },
                    "frequency_features": {
                        "enable": True,
                        "window_size": "5min"
                    },
                    "sequence_features": {
                        "enable": False,
                        "window_size": 10
                    },
                    "semantic_features": {
                        "enable": False,
                        "method": "tfidf",  # or "word2vec", "bert"
                        "max_features": 100
                    }
                }
        """
        self.config = config or {}
        
        # 1. 文本特征配置
        text_config = self.config.get("text_features", {})
        self.enable_text_features = text_config.get("enable", True)
        self.text_feature_types = text_config.get("features", [
            "length", "token_count", "digit_ratio", "special_char_ratio",
            "uppercase_ratio", "avg_token_length"
        ])
        
        # 2. 时间特征配置
        time_config = self.config.get("time_features", {})
        self.enable_time_features = time_config.get("enable", True)
        self.datetime_column = time_config.get("datetime_column", "timestamp")
        self.cyclical_features = time_config.get("cyclical_features", ["hour", "day_of_week"])
        self.time_interval_features = time_config.get("interval_features", True)
        
        # 3. 日志级别特征配置
        level_config = self.config.get("level_features", {})
        self.enable_level_features = level_config.get("enable", True)
        self.level_column = level_config.get("level_column", "level")
        self.level_mapping = level_config.get("level_mapping", {
            "DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2,
            "ERROR": 3, "FATAL": 4, "CRITICAL": 4
        })
        
        # 4. 频率特征配置
        freq_config = self.config.get("frequency_features", {})
        self.enable_frequency_features = freq_config.get("enable", True)
        self.freq_window_size = freq_config.get("window_size", "5min")
        
        # 5. 序列特征配置
        seq_config = self.config.get("sequence_features", {})
        self.enable_sequence_features = seq_config.get("enable", False)
        self.sequence_window = seq_config.get("window_size", 10)
        
        # 6. 语义特征配置
        semantic_config = self.config.get("semantic_features", {})
        self.enable_semantic_features = semantic_config.get("enable", False)
        self.semantic_method = semantic_config.get("method", "tfidf")
        self.max_semantic_features = semantic_config.get("max_features", 100)

        # 状态变量
        self.datetime_transformer = None
        self.tfidf_vectorizer = None
        self.is_fitted = False
        self.feature_names_ = []
        self.log_frequency_map_ = {}
        
        logger.info(f"LogFeatureEngineer initialized")
        logger.info(f"  - Text features: {self.enable_text_features}")
        logger.info(f"  - Time features: {self.enable_time_features}")
        logger.info(f"  - Level features: {self.enable_level_features}")
        logger.info(f"  - Frequency features: {self.enable_frequency_features}")
        logger.info(f"  - Sequence features: {self.enable_sequence_features}")
        logger.info(f"  - Semantic features: {self.enable_semantic_features}")

    def fit(self, df: pd.DataFrame) -> "LogFeatureEngineer":
        """
        拟合特征工程器（学习数据统计信息）

        Args:
            df: DataFrame with log data
                必需列: 'content' (日志文本)
                可选列: 'timestamp' (时间戳), 'level' (日志级别)

        Returns:
            Self
        """
        logger.info(f"Fitting LogFeatureEngineer on {len(df)} logs...")
        
        if 'content' not in df.columns:
            raise ValueError("DataFrame必须包含 'content' 列")
        
        # 1. 拟合时间特征转换器
        if self.enable_time_features and self.datetime_column in df.columns:
            self._fit_time_transformer(df)
        
        # 2. 计算日志频率统计（用于频率特征）
        if self.enable_frequency_features:
            self._fit_frequency_statistics(df)
        
        # 3. 拟合语义特征转换器
        if self.enable_semantic_features:
            self._fit_semantic_transformer(df)
        
        self.is_fitted = True
        logger.info("LogFeatureEngineer fitted successfully")
        return self
    
    def _fit_time_transformer(self, df: pd.DataFrame):
        """拟合时间特征转换器"""
        if self.datetime_column not in df.columns:
            logger.warning(f"时间列 '{self.datetime_column}' 不存在，跳过时间特征")
            return
        
        try:
            # 确保时间列是 datetime 类型
            if not pd.api.types.is_datetime64_any_dtype(df[self.datetime_column]):
                df[self.datetime_column] = pd.to_datetime(df[self.datetime_column])
            
            # 初始化 DatetimeFeatures 转换器
            self.datetime_transformer = DatetimeFeatures(
                variables=[self.datetime_column],
                features_to_extract=self._get_features_to_extract(),
                drop_original=False,
            )
            self.datetime_transformer.fit(df)
            logger.info(f"时间特征转换器已拟合: {self._get_features_to_extract()}")
        except Exception as e:
            logger.warning(f"时间特征转换器拟合失败: {e}")
            self.datetime_transformer = None
    
    def _fit_frequency_statistics(self, df: pd.DataFrame):
        """计算日志频率统计"""
        try:
            # 统计每种日志的出现频率
            log_counts = Counter(df['content'].tolist())
            total_logs = len(df)
            
            # 计算频率和罕见度
            self.log_frequency_map_ = {
                log: {
                    'count': count,
                    'frequency': count / total_logs,
                    'rarity': 1 / (count + 1)  # 罕见度：出现次数越少越罕见
                }
                for log, count in log_counts.items()
            }
            
            logger.info(f"频率统计已计算: 共 {len(self.log_frequency_map_)} 种不同日志")
        except Exception as e:
            logger.warning(f"频率统计计算失败: {e}")
            self.log_frequency_map_ = {}
    
    def _fit_semantic_transformer(self, df: pd.DataFrame):
        """拟合语义特征转换器"""
        if self.semantic_method == "tfidf":
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                
                self.tfidf_vectorizer = TfidfVectorizer(
                    max_features=self.max_semantic_features,
                    min_df=2,
                    max_df=0.8,
                    ngram_range=(1, 2)
                )
                self.tfidf_vectorizer.fit(df['content'])
                logger.info(f"TF-IDF转换器已拟合: {self.max_semantic_features} 特征")
            except Exception as e:
                logger.warning(f"TF-IDF转换器拟合失败: {e}")
                self.tfidf_vectorizer = None
        else:
            logger.warning(f"不支持的语义特征方法: {self.semantic_method}")

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        转换数据，提取所有配置的特征

        Args:
            df: DataFrame with log data
                必需列: 'content' (日志文本)
                可选列: 'timestamp', 'level'

        Returns:
            DataFrame with extracted features
        """
        if not self.is_fitted:
            raise RuntimeError("必须先调用 fit() 方法")
        
        logger.info(f"Transforming {len(df)} logs...")
        df_features = df.copy()
        feature_count = 0
        
        # 1. 文本统计特征
        if self.enable_text_features:
            df_features = self._extract_text_features(df_features)
            text_cols = [col for col in df_features.columns if col.startswith('text_')]
            feature_count += len(text_cols)
            logger.debug(f"提取文本特征: {len(text_cols)} 个")
        
        # 2. 时间特征
        if self.enable_time_features and self.datetime_transformer:
            df_features = self._extract_time_features(df_features)
            time_cols = [col for col in df_features.columns if col.startswith(self.datetime_column)]
            feature_count += len(time_cols)
            logger.debug(f"提取时间特征: {len(time_cols)} 个")
        
        # 3. 日志级别特征
        if self.enable_level_features and self.level_column in df_features.columns:
            df_features = self._extract_level_features(df_features)
            level_cols = [col for col in df_features.columns if col.startswith('level_')]
            feature_count += len(level_cols)
            logger.debug(f"提取级别特征: {len(level_cols)} 个")
        
        # 4. 频率特征
        if self.enable_frequency_features:
            df_features = self._extract_frequency_features(df_features)
            freq_cols = [col for col in df_features.columns if col.startswith('freq_')]
            feature_count += len(freq_cols)
            logger.debug(f"提取频率特征: {len(freq_cols)} 个")
        
        # 5. 序列特征
        if self.enable_sequence_features:
            df_features = self._extract_sequence_features(df_features)
            seq_cols = [col for col in df_features.columns if col.startswith('seq_')]
            feature_count += len(seq_cols)
            logger.debug(f"提取序列特征: {len(seq_cols)} 个")
        
        # 6. 语义特征
        if self.enable_semantic_features and self.tfidf_vectorizer:
            df_features = self._extract_semantic_features(df_features)
            semantic_cols = [col for col in df_features.columns if col.startswith('tfidf_')]
            feature_count += len(semantic_cols)
            logger.debug(f"提取语义特征: {len(semantic_cols)} 个")
        
        # 记录所有特征名
        self.feature_names_ = [col for col in df_features.columns if col not in df.columns]
        
        logger.info(f"特征提取完成: 共 {feature_count} 个特征")
        return df_features

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        拟合并转换数据

        Args:
            df: DataFrame with log data

        Returns:
            DataFrame with extracted features
        """
        self.fit(df)
        return self.transform(df)
    
    # ==================== 特征提取方法 ====================
    
    def _extract_text_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取文本统计特征
        
        特征列表：
        - text_length: 日志长度
        - text_token_count: token数量（空格分割）
        - text_digit_ratio: 数字字符比例
        - text_special_char_ratio: 特殊字符比例
        - text_uppercase_ratio: 大写字母比例
        - text_avg_token_length: 平均token长度
        """
        content = df['content'].astype(str)
        
        if "length" in self.text_feature_types:
            df['text_length'] = content.str.len()
        
        if "token_count" in self.text_feature_types:
            df['text_token_count'] = content.str.split().str.len()
        
        if "digit_ratio" in self.text_feature_types:
            digit_counts = content.apply(lambda x: sum(c.isdigit() for c in x))
            df['text_digit_ratio'] = digit_counts / (df['text_length'] + 1)
        
        if "special_char_ratio" in self.text_feature_types:
            special_counts = content.apply(lambda x: sum(not c.isalnum() and not c.isspace() for c in x))
            df['text_special_char_ratio'] = special_counts / (df['text_length'] + 1)
        
        if "uppercase_ratio" in self.text_feature_types:
            upper_counts = content.apply(lambda x: sum(c.isupper() for c in x))
            df['text_uppercase_ratio'] = upper_counts / (df['text_length'] + 1)
        
        if "avg_token_length" in self.text_feature_types:
            tokens = content.str.split()
            df['text_avg_token_length'] = tokens.apply(
                lambda t_list: np.mean([len(t) for t in t_list]) if t_list else 0
            )
        
        return df
    
    def _extract_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取时间特征
        
        特征列表：
        - timestamp_hour/day_of_week/etc: 时间组件
        - timestamp_*_sin/cos: 周期性编码
        - time_interval: 与前一条日志的时间间隔（秒）
        """
        if self.datetime_column not in df.columns:
            return df
        
        try:
            # 1. 基础时间特征
            df_time = self.datetime_transformer.transform(df)
            
            # 2. 周期性编码
            df_time = self._add_cyclical_encoding(df_time)
            
            # 3. 时间间隔特征
            if self.time_interval_features:
                time_col = df_time[self.datetime_column]
                if pd.api.types.is_datetime64_any_dtype(time_col):
                    # 计算时间间隔（秒）
                    time_diff = time_col.diff().dt.total_seconds()
                    df_time['time_interval'] = time_diff.fillna(0)
                    
                    # 时间间隔的统计特征
                    df_time['time_interval_log'] = np.log1p(df_time['time_interval'].clip(lower=0))
            
            return df_time
        except Exception as e:
            logger.warning(f"时间特征提取失败: {e}")
            return df
    
    def _extract_level_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取日志级别特征
        
        特征列表：
        - level_numeric: 级别的数值编码 (DEBUG=0, INFO=1, WARN=2, ERROR=3, FATAL=4)
        - level_is_error: 是否为错误级别 (ERROR/FATAL)
        - level_is_warning: 是否为警告级别 (WARN/WARNING)
        """
        if self.level_column not in df.columns:
            return df
        
        try:
            level_str = df[self.level_column].astype(str).str.upper()
            
            # 1. 数值编码
            df['level_numeric'] = level_str.map(self.level_mapping).fillna(1)  # 默认INFO
            
            # 2. 二值特征
            df['level_is_error'] = level_str.isin(['ERROR', 'FATAL', 'CRITICAL']).astype(int)
            df['level_is_warning'] = level_str.isin(['WARN', 'WARNING']).astype(int)
            
            # 3. 严重度分数（归一化）
            max_level = max(self.level_mapping.values())
            df['level_severity'] = df['level_numeric'] / max_level
            
            return df
        except Exception as e:
            logger.warning(f"级别特征提取失败: {e}")
            return df
    
    def _extract_frequency_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取频率特征
        
        特征列表：
        - freq_count: 该日志在训练集中的出现次数
        - freq_rate: 该日志的出现频率
        - freq_rarity: 该日志的罕见度（1/count）
        - freq_is_rare: 是否为罕见日志（出现次数<5）
        - freq_window_count: 时间窗口内的日志数量（如果有时间戳）
        """
        try:
            content = df['content']
            
            # 1. 全局频率特征
            df['freq_count'] = content.map(
                lambda x: self.log_frequency_map_.get(x, {}).get('count', 0)
            )
            df['freq_rate'] = content.map(
                lambda x: self.log_frequency_map_.get(x, {}).get('frequency', 0)
            )
            df['freq_rarity'] = content.map(
                lambda x: self.log_frequency_map_.get(x, {}).get('rarity', 1)
            )
            
            # 2. 罕见日志标记
            df['freq_is_rare'] = (df['freq_count'] < 5).astype(int)
            
            # 3. 时间窗口内的频率（如果有时间戳）
            if self.datetime_column in df.columns and pd.api.types.is_datetime64_any_dtype(df[self.datetime_column]):
                # 按时间窗口统计日志数量
                df_sorted = df.sort_values(self.datetime_column)
                df_sorted['freq_window_count'] = df_sorted.groupby(
                    pd.Grouper(key=self.datetime_column, freq=self.freq_window_size)
                ).cumcount() + 1
                df['freq_window_count'] = df_sorted['freq_window_count']
            
            return df
        except Exception as e:
            logger.warning(f"频率特征提取失败: {e}")
            return df
    
    def _extract_sequence_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取序列特征（日志前后关系）
        
        特征列表：
        - seq_position: 日志在序列中的位置（归一化）
        - seq_is_first: 是否为序列首条日志
        - seq_is_last: 是否为序列末条日志
        - seq_prev_same: 前一条日志是否相同
        - seq_next_same: 后一条日志是否相同
        
        注意：序列特征需要保持数据的时间顺序
        """
        try:
            total_logs = len(df)
            
            # 1. 位置特征
            df['seq_position'] = np.arange(total_logs) / max(total_logs - 1, 1)
            df['seq_is_first'] = (df.index == df.index[0]).astype(int)
            df['seq_is_last'] = (df.index == df.index[-1]).astype(int)
            
            # 2. 相邻日志特征
            content = df['content']
            df['seq_prev_same'] = (content == content.shift(1)).astype(int)
            df['seq_next_same'] = (content == content.shift(-1)).astype(int)
            
            # 3. 滑动窗口内的重复次数
            df['seq_repeat_in_window'] = content.rolling(
                window=self.sequence_window, min_periods=1
            ).apply(lambda x: (x == x.iloc[-1]).sum() - 1)
            
            return df
        except Exception as e:
            logger.warning(f"序列特征提取失败: {e}")
            return df
    
    def _extract_semantic_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取语义特征（文本向量化）
        
        特征列表：
        - tfidf_0 ~ tfidf_N: TF-IDF特征
        
        注意：语义特征计算密集，可能显著增加训练时间
        """
        if not self.tfidf_vectorizer:
            return df
        
        try:
            # 使用 TF-IDF 向量化
            tfidf_matrix = self.tfidf_vectorizer.transform(df['content'])
            tfidf_df = pd.DataFrame(
                tfidf_matrix.toarray(),
                columns=[f'tfidf_{i}' for i in range(tfidf_matrix.shape[1])],
                index=df.index
            )
            
            # 合并到原数据
            df_semantic = pd.concat([df, tfidf_df], axis=1)
            
            return df_semantic
        except Exception as e:
            logger.warning(f"语义特征提取失败: {e}")
            return df

    
    # ==================== 辅助方法 ====================
    
    def _get_features_to_extract(self) -> List[str]:
        """
        获取要提取的时间特征列表

        Returns:
            List of feature names
        """
        # 映射配置到 feature-engine 的特征名
        feature_mapping = {
            "hour": "hour",
            "day_of_week": "day_of_week",
            "day": "day",
            "month": "month",
            "year": "year",
            "minute": "minute",
            "second": "second",
            "week": "week",
        }

        features = []
        for feature in self.cyclical_features:
            if feature in feature_mapping:
                features.append(feature_mapping[feature])
            else:
                logger.warning(f"未知的周期性特征: {feature}")

        # 默认提取这些特征用于周期性编码
        if not features:
            features = ["hour", "day_of_week"]

        return features

    def _add_cyclical_encoding(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        添加周期性编码（sin/cos 变换）
        
        将时间特征转换为正弦/余弦表示，保留周期性信息。
        例如：23点和0点在数值上差距大，但在周期上很接近。
        
        Args:
            df: DataFrame with extracted time features

        Returns:
            DataFrame with cyclical encodings
        """
        for feature in self.cyclical_features:
            col_name = f"{self.datetime_column}_{feature}"

            if col_name not in df.columns:
                continue

            # 确定周期
            if feature == "hour":
                period = 24
            elif feature == "day_of_week":
                period = 7
            elif feature == "day":
                period = 31
            elif feature == "month":
                period = 12
            elif feature == "minute":
                period = 60
            elif feature == "second":
                period = 60
            elif feature == "week":
                period = 53
            else:
                logger.warning(f"未知周期: {feature}")
                continue

            # 添加 sin/cos 编码
            df[f"{col_name}_sin"] = np.sin(2 * np.pi * df[col_name] / period)
            df[f"{col_name}_cos"] = np.cos(2 * np.pi * df[col_name] / period)

        return df

    def get_feature_names(self) -> List[str]:
        """
        获取所有生成的特征名

        Returns:
            List of feature names
        """
        return self.feature_names_
    
    def get_feature_importance_map(self, importance_values: np.ndarray) -> Dict[str, float]:
        """
        将特征重要性值映射到特征名
        
        Args:
            importance_values: 特征重要性数组
            
        Returns:
            特征名到重要性的映射字典
        """
        if len(importance_values) != len(self.feature_names_):
            logger.warning(
                f"重要性数组长度 ({len(importance_values)}) 与特征数量 ({len(self.feature_names_)}) 不匹配"
            )
            return {}
        
        return dict(zip(self.feature_names_, importance_values))
    
    def get_feature_stats(self) -> Dict[str, Any]:
        """
        获取特征工程统计信息
        
        Returns:
            统计信息字典
        """
        return {
            'total_features': len(self.feature_names_),
            'text_features_enabled': self.enable_text_features,
            'time_features_enabled': self.enable_time_features,
            'level_features_enabled': self.enable_level_features,
            'frequency_features_enabled': self.enable_frequency_features,
            'sequence_features_enabled': self.enable_sequence_features,
            'semantic_features_enabled': self.enable_semantic_features,
            'feature_names': self.feature_names_,
        }
    
    def __repr__(self) -> str:
        """字符串表示"""
        status = "fitted" if self.is_fitted else "not fitted"
        n_features = len(self.feature_names_) if self.is_fitted else 0
        return f"LogFeatureEngineer({status}, {n_features} features)"



# ==================== 工具函数 ====================

def prepare_log_dataframe(
    logs: List[str],
    timestamps: Optional[List[str]] = None,
    labels: Optional[List[int]] = None,
    levels: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    准备日志数据为 DataFrame 格式
    
    Args:
        logs: 日志消息列表
        timestamps: 时间戳列表（可选）
        labels: 标签列表，用于有监督学习（可选）
        levels: 日志级别列表（可选）

    Returns:
        DataFrame with log data
        
    Example:
        >>> logs = ["Error in module A", "Warning: disk full"]
        >>> timestamps = ["2024-01-01 10:00:00", "2024-01-01 10:01:00"]
        >>> levels = ["ERROR", "WARN"]
        >>> df = prepare_log_dataframe(logs, timestamps, levels=levels)
    """
    data = {"content": logs}

    if timestamps:
        if len(timestamps) != len(logs):
            raise ValueError("时间戳数量必须与日志数量一致")
        data["timestamp"] = pd.to_datetime(timestamps)

    if labels:
        if len(labels) != len(logs):
            raise ValueError("标签数量必须与日志数量一致")
        data["label"] = labels
    
    if levels:
        if len(levels) != len(logs):
            raise ValueError("级别数量必须与日志数量一致")
        data["level"] = levels

    df = pd.DataFrame(data)
    logger.info(f"创建 DataFrame: {len(df)} 行, 列: {df.columns.tolist()}")

    return df


def get_default_config() -> Dict[str, Any]:
    """
    获取默认的特征工程配置
    
    Returns:
        默认配置字典
        
    Example:
        >>> config = get_default_config()
        >>> engineer = LogFeatureEngineer(config)
    """
    return {
        "text_features": {
            "enable": True,
            "features": [
                "length", 
                "token_count", 
                "digit_ratio", 
                "special_char_ratio",
                "uppercase_ratio", 
                "avg_token_length"
            ]
        },
        "time_features": {
            "enable": True,
            "datetime_column": "timestamp",
            "cyclical_features": ["hour", "day_of_week"],
            "interval_features": True
        },
        "level_features": {
            "enable": True,
            "level_column": "level",
            "level_mapping": {
                "DEBUG": 0, 
                "INFO": 1, 
                "WARN": 2, 
                "WARNING": 2,
                "ERROR": 3, 
                "FATAL": 4, 
                "CRITICAL": 4
            }
        },
        "frequency_features": {
            "enable": True,
            "window_size": "5min"
        },
        "sequence_features": {
            "enable": False,  # 计算密集型
            "window_size": 10
        },
        "semantic_features": {
            "enable": False,  # 计算密集型
            "method": "tfidf",
            "max_features": 100
        }
    }


def create_minimal_config() -> Dict[str, Any]:
    """
    创建最小化配置（仅启用文本和时间特征）
    
    适用于基于模板的方法（如 Spell/Drain）
    
    Returns:
        最小化配置字典
    """
    return {
        "text_features": {
            "enable": True,
            "features": ["length", "token_count"]
        },
        "time_features": {
            "enable": True,
            "datetime_column": "timestamp",
            "cyclical_features": ["hour"],
            "interval_features": False
        },
        "level_features": {"enable": False},
        "frequency_features": {"enable": False},
        "sequence_features": {"enable": False},
        "semantic_features": {"enable": False}
    }


def create_full_config() -> Dict[str, Any]:
    """
    创建完整配置（启用所有特征）
    
    适用于深度学习方法（如 LogBERT/DeepLog）
    
    Returns:
        完整配置字典
    """
    config = get_default_config()
    config["sequence_features"]["enable"] = True
    config["semantic_features"]["enable"] = True
    return config
