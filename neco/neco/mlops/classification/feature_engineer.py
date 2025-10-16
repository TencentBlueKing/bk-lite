"""分类任务特征工程模块 - 简化版本"""
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder, OneHotEncoder


class ClassificationFeatureEngineer:
    """简单特征工程器 - 渐进式设计"""
    
    def __init__(self, ordinal_features=None):
        """
        Args:
            ordinal_features: 有序特征 {'education': ['bachelor', 'master', 'phd']}
            其他特征类型自动检测：
            - 数值特征：自动识别数值类型
            - 类别特征：自动识别非数值非有序的特征  
            - 二元特征：自动识别只有2个值的特征
        """
        self.ordinal_features = ordinal_features or {}
        
        # 编码器
        self.encoders = {}
        self.scaler = None
    def _encode_features(self, X: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """特征编码 - 自动检测特征类型"""
        X = X.copy()
        
        if fit:
            # 1. 处理用户指定的有序特征
            for col, order in self.ordinal_features.items():
                if col in X.columns:
                    mapping = {val: i for i, val in enumerate(order)}
                    X[col] = X[col].map(mapping).fillna(-1)
            
            # 2. 自动检测并处理类别特征（非数值且非有序的特征）
            cat_cols = []
            for col in X.columns:
                if (not pd.api.types.is_numeric_dtype(X[col]) and 
                    col not in self.ordinal_features and
                    X[col].nunique() > 2):  # 二元特征单独处理
                    cat_cols.append(col)
            
            if cat_cols:
                encoder = OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore')
                encoded = encoder.fit_transform(X[cat_cols])
                
                # 生成新列名
                feature_names = []
                for i, col in enumerate(cat_cols):
                    for cat in encoder.categories_[i][1:]:  # skip first due to drop='first'
                        feature_names.append(f"{col}_{cat}")
                
                # 替换原列
                encoded_df = pd.DataFrame(encoded, columns=feature_names, index=X.index)
                X = X.drop(cat_cols, axis=1)
                X = pd.concat([X, encoded_df], axis=1)
                
                self.encoders['categorical'] = (encoder, cat_cols, feature_names)
            
            # 3. 处理二元特征（自动检测：只有2个值的非数值特征）
            binary_cols = []
            for col in X.columns:
                if (not pd.api.types.is_numeric_dtype(X[col]) and 
                    col not in self.ordinal_features and
                    X[col].nunique() == 2):
                    binary_cols.append(col)
            
            if binary_cols:
                from sklearn.preprocessing import LabelEncoder
                for col in binary_cols:
                    le = LabelEncoder()
                    X[col] = le.fit_transform(X[col].astype(str))
                    self.encoders[f'binary_{col}'] = le
        
        else:
            # 推理模式 - 应用已训练的编码器
            # 处理有序特征
            for col, order in self.ordinal_features.items():
                if col in X.columns:
                    mapping = {val: i for i, val in enumerate(order)}
                    X[col] = X[col].map(mapping).fillna(-1)
            
            # 处理类别特征
            if 'categorical' in self.encoders:
                encoder, cat_cols, feature_names = self.encoders['categorical']
                available_cols = [col for col in cat_cols if col in X.columns]
                
                if available_cols:
                    encoded = encoder.transform(X[available_cols])
                    encoded_df = pd.DataFrame(encoded, columns=feature_names, index=X.index)
                    X = X.drop(available_cols, axis=1)
                    X = pd.concat([X, encoded_df], axis=1)
            
            # 处理二元特征
            for key, encoder in self.encoders.items():
                if key.startswith('binary_'):
                    col = key.replace('binary_', '')
                    if col in X.columns:
                        X[col] = encoder.transform(X[col].astype(str))
        
        return X

    def _scale_features(self, X: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """特征缩放 - 简单的标准化"""
        numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return X
        
        if fit:
            self.scaler = StandardScaler()
            X[numeric_cols] = self.scaler.fit_transform(X[numeric_cols])
        else:
            if self.scaler:
                X[numeric_cols] = self.scaler.transform(X[numeric_cols])
        
        return X
    def extract_features(self, df: pd.DataFrame, selected_features=None, extract_labels=True):
        """特征提取 - 简化流程"""
        df = df.copy()
        
        # 提取标签
        y = None
        if extract_labels and 'label' in df.columns:
            y = df['label']
            X = df.drop('label', axis=1)
        else:
            X = df.drop('label', axis=1) if 'label' in df.columns else df
        
        # 推理模式
        if selected_features is not None:
            X = self._encode_features(X, fit=False)
            X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
            X = self._scale_features(X, fit=False)
            
            # 确保包含所需特征
            for feat in selected_features:
                if feat not in X.columns:
                    X[feat] = 0
            
            return X[selected_features], y, selected_features
        
        # 训练模式 - 简化流程：用全部特征，不做特征选择
        X = self._encode_features(X, fit=True)
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)  # 处理异常值
        X = self._scale_features(X, fit=True)
        
        return X, y, list(X.columns)