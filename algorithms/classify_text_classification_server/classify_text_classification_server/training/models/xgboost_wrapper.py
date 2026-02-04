"""MLflow 推理包装器"""
from typing import Dict, Any, List
import pandas as pd
import mlflow
from loguru import logger


class XGBoostWrapper(mlflow.pyfunc.PythonModel):
    """XGBoost 文本分类 MLflow 推理包装器
    
    封装完整的推理流程：
    1. 原始文本预处理（ChineseTextPreprocessor）
    2. 特征工程（TextFeatureEngineer）
    3. XGBoost 预测
    4. 标签解码（LabelEncoder）
    """
    
    def __init__(
        self,
        model,
        preprocessor,
        feature_engineer,
        label_encoder
    ):
        """初始化推理包装器
        
        Args:
            model: XGBoost 模型对象
            preprocessor: ChineseTextPreprocessor 实例
            feature_engineer: TextFeatureEngineer 实例
            label_encoder: LabelEncoder 实例
        """
        self.model = model
        self.preprocessor = preprocessor
        self.feature_engineer = feature_engineer
        self.label_encoder = label_encoder
        
        logger.info("XGBoostWrapper 初始化完成")
    
    def predict(self, context, model_input) -> pd.DataFrame:
        """端到端推理
        
        Args:
            context: MLflow 上下文（未使用）
            model_input: 输入数据，可以是：
                - pd.DataFrame: 包含 'text' 列
                - pd.Series: 文本序列
                - List[str]: 文本列表
                - str: 单条文本
                
        Returns:
            预测结果 DataFrame，包含：
            - prediction: 预测的类别标签（原始标签）
            - prediction_encoded: 预测的类别标签（编码后的整数）
            - probability: 预测概率（最高概率）
            - probabilities: 所有类别的概率分布
        """
        # 1. 提取文本
        texts = self._extract_texts(model_input)
        
        if not texts:
            raise ValueError("输入数据为空")
        
        logger.info(f"推理样本数: {len(texts)}")
        
        # 2. 文本预处理
        processed_texts = self.preprocessor.preprocess_batch(texts)
        
        # 3. 特征工程
        # 注意：需要同时传入原始文本用于统计特征提取
        features = self.feature_engineer.transform(
            processed_texts,
            original_texts=texts
        )
        
        # 4. 模型预测
        predictions_encoded = self.model.predict(features)
        probabilities = self.model.predict_proba(features)
        
        # 5. 标签解码
        predictions = self.label_encoder.inverse_transform(predictions_encoded)
        
        # 6. 构建结果
        results = pd.DataFrame({
            "prediction": predictions,
            "prediction_encoded": predictions_encoded,
            "probability": probabilities.max(axis=1),
        })
        
        # 添加所有类别的概率
        for i, class_name in enumerate(self.label_encoder.classes_):
            results[f"prob_{class_name}"] = probabilities[:, i]
        
        logger.info(f"推理完成，结果形状: {results.shape}")
        
        return results
    
    def _extract_texts(self, model_input) -> List[str]:
        """从输入中提取文本列表
        
        Args:
            model_input: 输入数据
            
        Returns:
            文本列表
        """
        # DataFrame
        if isinstance(model_input, pd.DataFrame):
            if "text" not in model_input.columns:
                raise ValueError("DataFrame 必须包含 'text' 列")
            return model_input["text"].tolist()
        
        # Series
        elif isinstance(model_input, pd.Series):
            return model_input.tolist()
        
        # List
        elif isinstance(model_input, list):
            return model_input
        
        # 单条文本
        elif isinstance(model_input, str):
            return [model_input]
        
        else:
            raise TypeError(f"不支持的输入类型: {type(model_input)}")


def create_mlflow_model(
    model,
    preprocessor,
    feature_engineer,
    label_encoder,
    conda_env: Dict[str, Any] = None
) -> mlflow.pyfunc.PythonModel:
    """创建 MLflow PyFunc 模型
    
    Args:
        model: XGBoost 模型
        preprocessor: 文本预处理器
        feature_engineer: 特征工程器
        label_encoder: 标签编码器
        conda_env: Conda 环境配置（可选）
        
    Returns:
        MLflow PyFunc 模型
    """
    wrapper = XGBoostWrapper(
        model=model,
        preprocessor=preprocessor,
        feature_engineer=feature_engineer,
        label_encoder=label_encoder
    )
    
    return wrapper
