import abc
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from loguru import logger
from hyperopt import fmin, tpe, Trials, space_eval
from sklearn.metrics import accuracy_score, classification_report, f1_score, roc_auc_score
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

from neco.mlops.classification.feature_engineer import ClassificationFeatureEngineer
from neco.mlops.utils.mlflow_utils import MLFlowUtils
from neco.mlops.utils.ml_utils import MLUtils


class BaseClassification(abc.ABC):
    """分类任务基类，提供通用的训练和预测功能"""

    def __init__(self):
        self.label_encoder = None
        self.class_names = None
        self.is_binary = None
        self.feature_engineer = None

    @abc.abstractmethod
    def build_model(self, train_params: dict):
        """构建模型实例"""
        pass

    def preprocess(self, df: pd.DataFrame, fit_encoder: bool = False) -> Tuple[pd.DataFrame, List[str]]:
        """数据预处理：缺失值处理、标签编码等"""
        if df is None or df.empty:
            raise ValueError("输入数据为空")

        df = df.copy()
        has_labels = 'label' in df.columns
        
        # 分离特征和标签
        features = df.drop('label', axis=1) if has_labels else df
        labels = df['label'] if has_labels else None

        # 处理数值特征缺失值
        numeric_cols = features.select_dtypes(include=[np.number]).columns
        features[numeric_cols] = features[numeric_cols].fillna(features[numeric_cols].median().fillna(0))
        
        # 处理类别特征缺失值和编码
        categorical_cols = features.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            features[col] = features[col].fillna(features[col].mode().iloc[0] if not features[col].mode().empty else 'unknown')
        
        if categorical_cols.any():
            features = pd.get_dummies(features, columns=categorical_cols, drop_first=True)

        # 标签编码
        if has_labels and fit_encoder:
            self.label_encoder = LabelEncoder()
            labels = pd.Series(self.label_encoder.fit_transform(labels))
            self.class_names = self.label_encoder.classes_
            self.is_binary = len(self.class_names) == 2
            logger.info(f"{'二' if self.is_binary else '多'}分类任务，{len(self.class_names)} 个类别: {list(self.class_names)}")
        elif has_labels and self.label_encoder:
            labels = pd.Series(self.label_encoder.transform(labels))

        # 重构数据
        if has_labels:
            features['label'] = labels
        
        feature_cols = [col for col in features.columns if col != 'label']
        logger.info(f"预处理完成: {len(feature_cols)} 个特征")

        return features, feature_cols

    def predict(self, data: pd.DataFrame, model_name: str, model_version: str = "latest", return_proba: bool = True):
        """使用训练好的模型进行分类预测"""
        model = MLFlowUtils.load_model(model_name, model_version)
        test_df, _ = self.preprocess(data, fit_encoder=False)
        
        # 使用简化的特征工程
        feature_engineer = ClassificationFeatureEngineer()
        X_test, _, _ = feature_engineer.extract_features(test_df, model.feature_cols, extract_labels=False)
        
        # 特征对齐：确保预测数据的特征与训练时完全一致
        if hasattr(model, 'feature_cols') and model.feature_cols:
            X_test_aligned = self._align_features(X_test, model.feature_cols)
        else:
            X_test_aligned = X_test
            
        result = pd.DataFrame({'predicted_label': model.predict(X_test_aligned)})
        
        if return_proba and hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X_test_aligned)
            for i, name in enumerate(getattr(model, 'class_names', [f'class_{i}' for i in range(proba.shape[1])])):
                if i < proba.shape[1]:
                    result[f'prob_{name}'] = proba[:, i]
        
        if hasattr(model, 'label_encoder') and model.label_encoder:
            result['predicted_label'] = model.label_encoder.inverse_transform(result['predicted_label'])
            
        return result

    def _align_features(self, X_test: pd.DataFrame, expected_features: list) -> pd.DataFrame:
        """
        对齐特征：确保预测数据的特征与训练时完全一致
        
        Args:
            X_test: 预测数据
            expected_features: 训练时的特征列表
            
        Returns:
            对齐后的预测数据
        """
        logger.info(f"特征对齐: 当前特征数={len(X_test.columns)}, 期望特征数={len(expected_features)}")
        
        # 创建与训练时特征完全一致的DataFrame
        aligned_data = pd.DataFrame(index=X_test.index)
        
        for feature in expected_features:
            if feature in X_test.columns:
                # 特征存在，直接复制
                aligned_data[feature] = X_test[feature]
            else:
                # 特征缺失，用0填充（对于独热编码的分类特征，缺失意味着该类别不存在）
                aligned_data[feature] = 0
                logger.debug(f"缺失特征 '{feature}' 已用0填充")
        
        # 检查是否有多余的特征（通常不应该有）
        extra_features = set(X_test.columns) - set(expected_features)
        if extra_features:
            logger.warning(f"发现多余特征: {extra_features}")
            
        logger.info(f"特征对齐完成: {aligned_data.shape}")
        return aligned_data

    def _get_metrics(self, y_true, y_pred, model=None, X=None):
        """计算评估指标"""
        from sklearn.metrics import precision_score, recall_score
        
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "f1_weighted": f1_score(y_true, y_pred, average='weighted'),
            "f1_macro": f1_score(y_true, y_pred, average='macro'),
            "precision_weighted": precision_score(y_true, y_pred, average='weighted', zero_division=0),
            "recall_weighted": recall_score(y_true, y_pred, average='weighted', zero_division=0)
        }
        
        if self.is_binary and model and X is not None:
            proba = MLUtils.get_prediction_scores(model, X)
            metrics["auc"] = roc_auc_score(y_true, proba)
            
        return {k: float(v) for k, v in metrics.items()}

    def _validate_input_data(
        self, 
        train_dataframe: pd.DataFrame, 
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None
    ):
        """验证输入数据的质量和格式"""
        
        # 检查训练数据
        if train_dataframe is None or train_dataframe.empty:
            raise ValueError("训练数据不能为空")
            
        if 'label' not in train_dataframe.columns:
            raise ValueError("训练数据必须包含 'label' 列")
            
        # 检查标签分布
        unique_labels = train_dataframe['label'].nunique()
        if unique_labels < 2:
            raise ValueError(f"标签类别数不足，至少需要2个类别，当前只有{unique_labels}个")
            
        # 检查样本数量
        min_samples_per_class = train_dataframe['label'].value_counts().min()
        if min_samples_per_class < 5:
            logger.warning(f"某些类别样本过少 (最少: {min_samples_per_class})，可能影响模型性能")
            
        # 检查数据一致性
        if val_dataframe is not None:
            self._check_data_consistency(train_dataframe, val_dataframe, "验证集")
            
        if test_dataframe is not None:
            self._check_data_consistency(train_dataframe, test_dataframe, "测试集")
            
        logger.info(f"数据验证通过 - 训练集: {len(train_dataframe)} 样本, {unique_labels} 个类别")

    def _check_data_consistency(self, train_df: pd.DataFrame, other_df: pd.DataFrame, dataset_name: str):
        """检查数据集之间的一致性"""
        if 'label' not in other_df.columns:
            raise ValueError(f"{dataset_name}必须包含 'label' 列")
            
        # 检查特征列一致性
        train_features = set(train_df.columns) - {'label'}
        other_features = set(other_df.columns) - {'label'}
        
        missing_in_other = train_features - other_features
        extra_in_other = other_features - train_features
        
        if missing_in_other:
            logger.warning(f"{dataset_name}缺少特征: {missing_in_other}")
        if extra_in_other:
            logger.warning(f"{dataset_name}多出特征: {extra_in_other}")
            
        # 检查标签一致性
        train_labels = set(train_df['label'].unique())
        other_labels = set(other_df['label'].unique())
        
        new_labels = other_labels - train_labels
        if new_labels:
            logger.warning(f"{dataset_name}包含训练集中没有的标签: {new_labels}")

    def _split_datasets(
        self, 
        train_df: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame],
        test_dataframe: Optional[pd.DataFrame],
        val_size: float,
        test_size: float,
        random_state: int
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.DataFrame]]:
        """
        智能数据分割 - 数据科学最佳实践
        
        当缺少验证集或测试集时，自动从训练数据中分割：
        1. 如果都没提供：train (60%) / val (20%) / test (20%)
        2. 如果只提供测试集：train (80%) / val (20%) / test (provided)  
        3. 如果只提供验证集：train (80%) / val (provided) / test (20%)
        4. 如果都提供：使用提供的数据集
        """
        
        # 记录原始数据量
        total_samples = len(train_df)
        logger.info(f"原始训练数据: {total_samples} 样本")
        
        # 情况1: 验证集和测试集都已提供
        if val_dataframe is not None and test_dataframe is not None:
            val_df = self.preprocess(val_dataframe)[0]
            test_df = self.preprocess(test_dataframe)[0]
            logger.info(f"使用提供的数据集 - 训练: {len(train_df)}, 验证: {len(val_df)}, 测试: {len(test_df)}")
            return train_df, val_df, test_df
        
        # 情况2: 只提供了验证集，需要分割出测试集
        elif val_dataframe is not None and test_dataframe is None:
            val_df = self.preprocess(val_dataframe)[0]
            # 从训练数据中分割出测试集
            train_df, test_df = train_test_split(
                train_df, 
                test_size=test_size, 
                random_state=random_state,
                stratify=train_df['label']
            )
            logger.info(f"提供验证集，从训练数据分割测试集 - 训练: {len(train_df)}, 验证: {len(val_df)}, 测试: {len(test_df)}")
            return train_df, val_df, test_df
        
        # 情况3: 只提供了测试集，需要分割出验证集
        elif val_dataframe is None and test_dataframe is not None:
            test_df = self.preprocess(test_dataframe)[0]
            # 从训练数据中分割出验证集
            train_df, val_df = train_test_split(
                train_df,
                test_size=val_size,
                random_state=random_state,
                stratify=train_df['label']
            )
            logger.info(f"提供测试集，从训练数据分割验证集 - 训练: {len(train_df)}, 验证: {len(val_df)}, 测试: {len(test_df)}")
            return train_df, val_df, test_df
        
        # 情况4: 验证集和测试集都没提供，需要从训练数据中分割两个集合
        else:
            # 先分割出测试集
            temp_train_df, test_df = train_test_split(
                train_df,
                test_size=test_size,
                random_state=random_state,
                stratify=train_df['label']
            )
            
            # 再从剩余数据中分割出验证集
            # 调整验证集大小，使其占原始数据的指定比例
            adjusted_val_size = val_size / (1 - test_size)
            final_train_df, val_df = train_test_split(
                temp_train_df,
                test_size=adjusted_val_size,
                random_state=random_state,
                stratify=temp_train_df['label']
            )
            
            logger.info(
                f"自动数据分割 - "
                f"训练: {len(final_train_df)} ({len(final_train_df)/total_samples:.1%}), "
                f"验证: {len(val_df)} ({len(val_df)/total_samples:.1%}), "
                f"测试: {len(test_df)} ({len(test_df)/total_samples:.1%})"
            )
            
            # 检查数据分布
            self._log_data_distribution(final_train_df, val_df, test_df)
            
            return final_train_df, val_df, test_df

    def _log_data_distribution(self, train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame):
        """记录各数据集的标签分布，确保分割合理"""
        try:
            train_dist = train_df['label'].value_counts(normalize=True).sort_index()
            val_dist = val_df['label'].value_counts(normalize=True).sort_index()
            test_dist = test_df['label'].value_counts(normalize=True).sort_index()
            
            logger.info("数据集标签分布检查:")
            for label in train_dist.index:
                logger.info(
                    f"  类别 {self.label_encoder.inverse_transform([label])[0] if self.label_encoder else label}: "
                    f"训练 {train_dist.get(label, 0):.3f}, "
                    f"验证 {val_dist.get(label, 0):.3f}, "
                    f"测试 {test_dist.get(label, 0):.3f}"
                )
                
            # 检查分布差异是否过大
            max_diff = max(
                abs(train_dist - val_dist).max(),
                abs(train_dist - test_dist).max(),
                abs(val_dist - test_dist).max()
            )
            
            if max_diff > 0.1:  # 10% 差异阈值
                logger.warning(f"数据集间标签分布差异较大 (最大差异: {max_diff:.3f})，建议检查数据质量")
            else:
                logger.info(f"数据集标签分布合理 (最大差异: {max_diff:.3f})")
                
        except Exception as e:
            logger.warning(f"无法计算数据分布: {e}")

    def _analyze_model_performance(self, val_metrics: dict, test_metrics: dict, n_features: int, n_samples: int) -> dict:
        """分析模型性能并给出改进建议"""
        analysis = {
            "model_complexity": "appropriate",
            "performance_level": "good",
            "recommendations": []
        }
        
        # 性能水平评估 (基于验证集)
        val_f1 = val_metrics.get('f1_weighted', 0)
        val_acc = val_metrics.get('accuracy', 0)
        
        if val_f1 < 0.6 or val_acc < 0.6:
            analysis["performance_level"] = "poor"
            analysis["recommendations"].extend([
                "考虑增加更多训练数据",
                "尝试特征工程或特征选择",
                "调整超参数搜索范围",
                "考虑使用更复杂的模型"
            ])
        elif val_f1 < 0.8 or val_acc < 0.8:
            analysis["performance_level"] = "moderate"
            analysis["recommendations"].extend([
                "可以尝试特征工程优化",
                "考虑增加超参数优化轮次"
            ])
        else:
            analysis["performance_level"] = "excellent"
        
        # 过拟合检测
        if test_metrics:
            val_test_diff = abs(val_metrics.get('f1_weighted', 0) - test_metrics.get('f1_weighted', 0))
            if val_test_diff > 0.1:
                analysis["overfitting_risk"] = "high"
                analysis["recommendations"].extend([
                    "模型可能过拟合，考虑正则化",
                    "增加训练数据或使用数据增强",
                    "简化模型复杂度"
                ])
            elif val_test_diff > 0.05:
                analysis["overfitting_risk"] = "moderate"
                analysis["recommendations"].append("轻微过拟合，建议监控")
            else:
                analysis["overfitting_risk"] = "low"
        
        # 数据量分析
        samples_per_feature = n_samples / n_features if n_features > 0 else 0
        if samples_per_feature < 10:
            analysis["data_sufficiency"] = "insufficient"
            analysis["recommendations"].extend([
                f"数据量相对特征数较少 (每特征{samples_per_feature:.1f}样本)",
                "考虑特征选择或降维",
                "增加训练数据"
            ])
        elif samples_per_feature < 50:
            analysis["data_sufficiency"] = "moderate"
            analysis["recommendations"].append("数据量适中，可考虑适当增加")
        else:
            analysis["data_sufficiency"] = "sufficient"
        
        return analysis

    def _log_training_summary(self, best_params: dict, val_metrics: dict, test_metrics: dict, analysis: dict):
        """输出训练总结"""
        logger.info("=" * 60)
        logger.info("训练完成总结")
        logger.info("=" * 60)
        
        logger.info(f"最佳超参数: {best_params}")
        logger.info(f"验证集性能: {val_metrics}")
        if test_metrics:
            logger.info(f"测试集性能: {test_metrics}")
        
        logger.info(f"性能水平: {analysis['performance_level']}")
        if analysis.get('overfitting_risk'):
            logger.info(f"过拟合风险: {analysis['overfitting_risk']}")
        
        if analysis.get('recommendations'):
            logger.info("改进建议:")
            for i, rec in enumerate(analysis['recommendations'], 1):
                logger.info(f"  {i}. {rec}")
        
        logger.info("=" * 60)

    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        train_config: Optional[dict] = None,
        max_evals: int = 50,
        primary_metric: str = "f1_weighted",
        # 特征配置
        ordinal_features: Optional[Dict[str, List]] = None,
        # 数据分割配置
        val_size: float = 0.2,
        test_size: float = 0.2,
        random_state: int = 42,
        # MLflow配置
        mlflow_tracking_url: Optional[str] = None,
        experiment_name: str = "Classification"
    ):
        """
        训练分类模型 - 数据科学最佳实践版本
        
        Args:
            model_name: 模型名称
            train_dataframe: 训练数据，必须包含 'label' 列
            val_dataframe: 验证数据 (可选)，如不提供将从训练数据中自动分割
            test_dataframe: 测试数据 (可选)，如不提供将从训练数据中自动分割
            train_config: 训练配置/超参数搜索空间
            max_evals: 超参数优化最大评估次数
            primary_metric: 主要评估指标 ('accuracy', 'f1_weighted', 'f1_macro', 'auc')
            ordinal_features: 有序特征配置 {'education': ['bachelor', 'master', 'phd']}
            val_size: 验证集占比 (当需要自动分割时)
            test_size: 测试集占比 (当需要自动分割时)  
            random_state: 随机种子，确保结果可复现
            mlflow_tracking_url: MLflow追踪服务URL
            experiment_name: 实验名称
            
        数据分割策略 (数据科学最佳实践):
            - 如果提供了验证集和测试集：直接使用
            - 如果只提供验证集：从训练数据中分割测试集
            - 如果只提供测试集：从训练数据中分割验证集
            - 如果都没提供：自动分割为 训练(60%)/验证(20%)/测试(20%)
            - 所有分割都使用分层抽样，保持标签分布一致
        """
        MLFlowUtils.setup_experiment(mlflow_tracking_url, experiment_name)

        # 数据验证
        self._validate_input_data(train_dataframe, val_dataframe, test_dataframe)
        
        # 数据预处理
        train_df, _ = self.preprocess(train_dataframe, fit_encoder=True)
        
        # 智能数据分割 - 数据科学最佳实践
        train_df, val_df, test_df = self._split_datasets(
            train_df, val_dataframe, test_dataframe, 
            val_size, test_size, random_state
        )

        # 特征工程 - 只需指定有序特征
        self.feature_engineer = ClassificationFeatureEngineer(ordinal_features)
        
        X_train, y_train, feature_cols = self.feature_engineer.extract_features(train_df)
        X_val, y_val, _ = self.feature_engineer.extract_features(val_df, selected_features=feature_cols)

        # 构建超参数搜索空间 (只构建一次，避免重复日志)
        search_space = MLUtils.build_search_space(train_config or {})

        # 超参数优化
        def objective(params_raw):
            try:
                params = space_eval(search_space, params_raw)
                model = self.build_model(params)
                model.fit(X_train, y_train)
                
                val_pred = model.predict(X_val)
                if primary_metric == "accuracy":
                    score = accuracy_score(y_val, val_pred)
                elif primary_metric == "auc" and self.is_binary:
                    score = roc_auc_score(y_val, MLUtils.get_prediction_scores(model, X_val))
                else:
                    avg = 'macro' if primary_metric == 'f1_macro' else 'weighted'
                    score = f1_score(y_val, val_pred, average=avg)
                
                return {"loss": -score, "status": "ok"}
            except:
                return {"loss": 1.0, "status": "ok"}

        # 优化并训练最终模型
        trials = Trials()
        best_params = space_eval(
            search_space,
            fmin(objective, search_space, 
                 algo=tpe.suggest, max_evals=max_evals, trials=trials, rstate=np.random.default_rng(42))
        )
        
        model = self.build_model(best_params)
        model.fit(X_train, y_train)
        
        # 设置模型属性
        model.feature_cols = feature_cols
        model.label_encoder = self.label_encoder
        model.class_names = self.class_names
        model.is_binary = self.is_binary

        # 评估
        val_metrics = self._get_metrics(y_val, model.predict(X_val), model, X_val)
        test_metrics = {}
        if test_df is not None:
            X_test, y_test, _ = self.feature_engineer.extract_features(test_df, selected_features=feature_cols)
            test_metrics = self._get_metrics(y_test, model.predict(X_test), model, X_test)

        # 性能分析和建议
        performance_analysis = self._analyze_model_performance(
            val_metrics, test_metrics, len(feature_cols), len(train_df)
        )
        
        # 记录结果
        MLFlowUtils.log_training_results(
            {**best_params, "max_evals": max_evals, "n_features": len(feature_cols), **performance_analysis},
            [], [], primary_metric, val_metrics, test_metrics, model, model_name
        )

        # 输出训练总结
        self._log_training_summary(best_params, val_metrics, test_metrics, performance_analysis)

        return {
            "model": model, 
            "params": best_params, 
            "val_metrics": val_metrics, 
            "test_metrics": test_metrics,
            "performance_analysis": performance_analysis
        }