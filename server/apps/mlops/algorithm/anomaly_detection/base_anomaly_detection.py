import abc
from math import log
from typing import Any, Dict
from functools import lru_cache
import time
import threading

from apps.mlops.models.anomaly_detection import AnomalyDetectionTrainJob
from config.components.mlflow import MLFLOW_TRACKER_URL
import mlflow
import json
import pandas as pd
import numpy as np
from hyperopt import hp, fmin, tpe, Trials, STATUS_OK
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, fbeta_score, balanced_accuracy_score
from imblearn.metrics import geometric_mean_score
from apps.core.logger import mlops_logger as logger


class BaseAnomalyDetection(abc.ABC):
    # 类级别的模型缓存，线程安全
    _model_cache = {}
    _cache_lock = threading.Lock()
    _cache_expiry_time = 3600  # 缓存过期时间（秒）

    def __init__(self):
        super().__init__()

    @classmethod
    def _get_cache_key(cls, model_name: str, model_version: str) -> str:
        """生成缓存键"""
        return f"{model_name}:{model_version}"

    @classmethod
    def _is_cache_valid(cls, cache_entry: dict) -> bool:
        """检查缓存是否有效"""
        if not cache_entry:
            return False

        current_time = time.time()
        cache_time = cache_entry.get('cached_at', 0)

        # 检查是否超过过期时间
        return (current_time - cache_time) < cls._cache_expiry_time

    @classmethod
    def _load_model_with_cache(cls, model_name: str, model_version: str):
        """
        带缓存的模型加载方法

        Args:
            model_name: 模型名称
            model_version: 模型版本

        Returns:
            加载的模型对象
        """
        cache_key = cls._get_cache_key(model_name, model_version)

        with cls._cache_lock:
            # 检查缓存是否存在且有效
            if cache_key in cls._model_cache and cls._is_cache_valid(cls._model_cache[cache_key]):
                logger.info(f"🎯 使用缓存模型: {model_name}:{model_version}")
                return cls._model_cache[cache_key]['model']

            # 缓存未命中或已过期，重新加载模型
            logger.info(f"📥 从MLflow加载模型: {model_name}:{model_version}")

            try:
                mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
                model_uri = f"models:/{model_name}/{model_version}"
                model = mlflow.sklearn.load_model(model_uri)

                # 更新缓存
                cls._model_cache[cache_key] = {
                    'model': model,
                    'cached_at': time.time(),
                    'model_name': model_name,
                    'model_version': model_version
                }

                logger.info(f"✅ 模型已缓存: {model_name}:{model_version}")
                return model

            except Exception as e:
                logger.error(f"❌ 模型加载失败: {model_name}:{model_version}, 错误: {str(e)}")
                raise

    @classmethod
    def clear_model_cache(cls, model_name: str = None, model_version: str = None):
        """
        清理模型缓存

        Args:
            model_name: 可选，指定要清理的模型名称
            model_version: 可选，指定要清理的模型版本
        """
        with cls._cache_lock:
            if model_name and model_version:
                # 清理指定模型
                cache_key = cls._get_cache_key(model_name, model_version)
                if cache_key in cls._model_cache:
                    del cls._model_cache[cache_key]
                    logger.info(f"🗑️  已清理指定模型缓存: {model_name}:{model_version}")
            else:
                # 清理所有缓存
                cls._model_cache.clear()
                logger.info(f"🗑️  已清理所有模型缓存")

    @classmethod
    def get_cache_info(cls) -> dict:
        """获取缓存信息用于监控"""
        with cls._cache_lock:
            cache_info = {
                'total_cached_models': len(cls._model_cache),
                'cache_expiry_seconds': cls._cache_expiry_time,
                'cached_models': []
            }

            current_time = time.time()
            for cache_key, cache_entry in cls._model_cache.items():
                cache_age = current_time - cache_entry.get('cached_at', 0)
                is_valid = cls._is_cache_valid(cache_entry)

                cache_info['cached_models'].append({
                    'model_name': cache_entry.get('model_name'),
                    'model_version': cache_entry.get('model_version'),
                    'cache_age_seconds': cache_age,
                    'is_valid': is_valid
                })

            return cache_info

    def calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray, subprefix: str) -> Dict[str, float]:
        """计算分类评估指标"""
        return {
            f"{subprefix}_accuracy": accuracy_score(y_true, y_pred),
            f"{subprefix}_precision": precision_score(y_true, y_pred, zero_division=0),
            f"{subprefix}_recall": recall_score(y_true, y_pred, zero_division=0),
            f"{subprefix}_f1": f1_score(y_true, y_pred, zero_division=0),
        }

    def prepare_features(cls, windows_size: int, df: pd.DataFrame, freq: str = 'infer') :
        # 确保timestamp列转换为datetime格式
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.set_index('timestamp')
        predict_freq = freq
        if freq == 'infer':
            predict_freq = pd.infer_freq(df.index)

        logger.info(f"🔍 指标间隔: {predict_freq}, 窗口大小: {windows_size}")
        df = df.asfreq(predict_freq)
        df['value'] = df['value'].interpolate('linear').bfill().ffill()

        # 计算滚动窗口统计量
        rolling = df['value'].rolling(windows_size, min_periods=1)
        df['rolling_mean'] = rolling.mean()
        df['rolling_std'] = rolling.std().fillna(1e-5)  # 避免除以0

        df_features = {
            # 原始值
            'value': df['value'],

            # 统计特征
            'rolling_min': rolling.min(),
            'rolling_max': rolling.max(),
            'rolling_median': rolling.median(),

            # 差分特征
            'diff_1': df['value'].diff().fillna(0),
            'diff_2': df['value'].diff().diff().fillna(0),

            # 归一化特征
            'zscore': (df['value'] - df['rolling_mean']) / df['rolling_std'],

            # 趋势特征
            'trend': rolling.apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) > 1 else 0),

            # 自相关特征
            'autocorr_1': df['value'].rolling(windows_size * 2, min_periods=windows_size)
            .apply(lambda x: x.autocorr(lag=1) if len(x) > windows_size else 0)
            if len(df) >= windows_size * 2 else pd.Series(0, index=df.index),

            # 时间特征
            'hour': df.index.hour,
            'minute': df.index.minute,
            'dayofweek': df.index.dayofweek,
            'month': df.index.month,
            'is_weekend': (df.index.dayofweek >= 5).astype(int),
        }

        features_df = pd.DataFrame(df_features, index=df.index)

        if 'label' in df.columns:
            features_df['label'] = df['label']

        features_df = features_df.dropna()

        feature_columns = [
            col for col in features_df.columns if col != 'label']
        return features_df, feature_columns, predict_freq

    def predict(self, data: pd.DataFrame, model_name: str, model_version: str = "latest") -> pd.DataFrame:
        """
        使用训练好的模型进行异常检测预测（带缓存优化）

        Args:
            data: 包含timestamp和value列的DataFrame
            model_name: 模型名称
            model_version: 模型版本，默认为latest

        Returns:
            包含预测结果的DataFrame
        """
        # 使用缓存机制加载模型
        model = self._load_model_with_cache(model_name, model_version)

        test_df, feature_columns, _ = self.prepare_features(model.window, data, model.freq)

        # 获取异常概率，处理单类别情况
        probabilities = model.predict_proba(test_df[feature_columns])[:, 1]
        return pd.DataFrame({
            'value': test_df['value'],
            'anomaly_probability': probabilities,
        })

    def train(
        self,
        entity: AnomalyDetectionTrainJob,
    ) -> None:
        mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
        experiment_name = f"{entity.id}_{entity.name}"
        mlflow.set_experiment(experiment_name)
        logger.info(f"🔍 开始训练任务: 实验: {experiment_name}")

        train_df = pd.DataFrame(entity.train_data_id.train_data)

        # 基于metadata中的异常点索引生成label列
        # 初始化所有点为正常（0）
        train_df['label'] = 0

        # 获取异常点索引列表
        anomaly_indices = entity.train_data_id.metadata['anomaly_point']
        if anomaly_indices and isinstance(anomaly_indices, list):
            # 将指定索引位置标记为异常（1）
            valid_indices = [idx for idx in anomaly_indices if 0 <= idx < len(train_df)]
            train_df.loc[valid_indices, 'label'] = 1
        train_df, feature_columns, freq = self.prepare_features(entity.windows_size, train_df)
        X_train, y_train = train_df[feature_columns].values, train_df['label'].values
        logger.info(f"📁 训练集: 样本数: {len(X_train)}")

        val_df = pd.DataFrame(entity.val_data_id.train_data)

        # 基于metadata中的异常点索引生成验证集label列
        # 初始化所有点为正常（0）
        val_df['label'] = 0

        # 获取验证集异常点索引列表
        val_anomaly_indices = entity.val_data_id.metadata['anomaly_point']
        if val_anomaly_indices and isinstance(val_anomaly_indices, list):
            # 将指定索引位置标记为异常（1）
            val_valid_indices = [idx for idx in val_anomaly_indices if 0 <= idx < len(val_df)]
            val_df.loc[val_valid_indices, 'label'] = 1

        val_df, _, _ = self.prepare_features(entity.windows_size, val_df)
        X_val, y_val = val_df[feature_columns].values, val_df['label'].values
        logger.info(f"📁 验证集: 样本数: {len(X_val)}")

        test_df = pd.DataFrame(entity.test_data_id.train_data)

        # 基于metadata中的异常点索引生成测试集label列
        # 初始化所有点为正常（0）
        test_df['label'] = 0

        # 获取测试集异常点索引列表
        test_anomaly_indices = entity.test_data_id.metadata['anomaly_point']
        if test_anomaly_indices and isinstance(test_anomaly_indices, list):
            # 将指定索引位置标记为异常（1）
            test_valid_indices = [idx for idx in test_anomaly_indices if 0 <= idx < len(test_df)]
            test_df.loc[test_valid_indices, 'label'] = 1

        test_df, _, _ = self.prepare_features(entity.windows_size, test_df)
        X_test, y_test = test_df[feature_columns].values, test_df['label'].values
        logger.info(f"📁 测试集: 样本数: {len(X_test)}")

        hyperopt_config = {}
        for key, value in entity.hyperopt_config.items():
            if value['type'] == 'randint':
                hyperopt_config[key] = hp.randint(key, value['min'], value['max'])
            if value['type'] == 'choice':
                options = []
                for choice in value['choice']:
                    if choice == 'none':
                        options.append(None)
                    elif choice == 'true':
                        options.append(True)
                    elif choice == 'false':
                        options.append(False)
                    else:
                        options.append(choice)
                hyperopt_config[key] = hp.choice(key, options)
        logger.info(f"🚀 超参数优化: 最大评估{entity.max_evals}")

        # 数据质量检查
        logger.info(f"🔍 数据质量检查:")

        # 检查特征是否包含异常值或常数列
        feature_stats = pd.DataFrame(train_df[feature_columns]).describe()
        constant_features = []
        for col in feature_columns:
            if train_df[col].nunique() <= 1:
                constant_features.append(col)

        if constant_features:
            logger.warning(f"⚠️  发现常数特征: {constant_features}")
            logger.warning(f"   这些特征可能影响模型训练效果")

        # 检查数据分布
        train_positive_ratio = np.mean(y_train)
        val_positive_ratio = np.mean(y_val)
        test_positive_ratio = np.mean(y_test)

        logger.info(f"📊 详细数据统计:")
        logger.info(f"   - 训练集: {len(X_train)} 样本, 异常: {int(train_positive_ratio * len(X_train))}, 比例: {train_positive_ratio:.4f}")
        logger.info(f"   - 验证集: {len(X_val)} 样本, 异常: {int(val_positive_ratio * len(X_val))}, 比例: {val_positive_ratio:.4f}")
        logger.info(f"   - 测试集: {len(X_test)} 样本, 异常: {int(test_positive_ratio * len(X_test))}, 比例: {test_positive_ratio:.4f}")

        # 分布一致性检查
        ratio_diff = max(abs(train_positive_ratio - val_positive_ratio),
                         abs(train_positive_ratio - test_positive_ratio),
                         abs(val_positive_ratio - test_positive_ratio))

        if ratio_diff > 0.2:
            logger.warning(f"⚠️  数据集间异常比例差异过大: {ratio_diff:.4f}")
            logger.warning(f"   可能影响模型泛化性能")

        # 特征值范围检查
        train_feature_ranges = pd.DataFrame(X_train).describe()
        extreme_features = []
        for i, col in enumerate(feature_columns):
            col_data = X_train[:, i]
            if np.any(np.isinf(col_data)) or np.any(np.isnan(col_data)):
                extreme_features.append(col)

        if extreme_features:
            logger.error(f"❌ 发现异常特征值: {extreme_features}")
            logger.error(f"   包含inf或nan值，需要数据预处理")

        trials = Trials()
        step_counter = 0
        best_loss = float('inf')
        best_model = None  # 在外部作用域保存最佳模型

        def objective(params: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal step_counter, best_loss, best_model
            step_counter += 1

            model = self.build_model(params)
            model.fit(X_train, y_train)

            # 验证集评估
            y_val_pred = model.predict(X_val)
            val_metrics = self.calculate_metrics(
                y_val, y_val_pred, subprefix='val')
            val_accuracy = (y_val == y_val_pred).mean()

            # 测试集评估（仅用于监控，不参与优化决策）
            y_test_pred = model.predict(X_test)
            test_metrics = self.calculate_metrics(
                y_test, y_test_pred, subprefix='test')
            test_accuracy = (y_test == y_test_pred).mean()

            # 获取基础指标
            recall = val_metrics.get('val_recall', 0.0)
            precision = val_metrics.get('val_precision', 0.0)
            f1 = val_metrics.get('val_f1', 0.0)

            # 计算类别分布信息
            positive_ratio = np.mean(y_val)  # 异常样本比例

            # 使用经典的异常检测损失函数 - 选择其中一种

            # 方案1: F-beta损失 (推荐用于异常检测，beta=2偏向召回率)
            fbeta_2 = fbeta_score(y_val, y_val_pred, beta=2, zero_division=0)
            current_loss = 1.0 - fbeta_2

            # 方案2: 几何平均损失 (对不平衡数据效果好)
            # geometric_mean = geometric_mean_score(y_val, y_val_pred)
            # current_loss = 1.0 - geometric_mean

            # 方案3: 平衡准确率损失 (sklearn内置，处理不平衡数据)
            # balanced_acc = balanced_accuracy_score(y_val, y_val_pred)
            # current_loss = 1.0 - balanced_acc

            # 方案4: Matthews相关系数损失 (对不平衡数据鲁棒)
            # from sklearn.metrics import matthews_corrcoef
            # mcc = matthews_corrcoef(y_val, y_val_pred)
            # current_loss = 1.0 - (mcc + 1) / 2  # 归一化到0-1

            # 方案5: 加权F1损失 (简单有效)
            # weight_recall = 0.7  # 异常检测偏向召回率
            # weight_precision = 0.3
            # weighted_f1 = 2 * (weight_recall * recall * weight_precision * precision) / \
            #               (weight_recall * recall + weight_precision * precision + 1e-8)
            # current_loss = 1.0 - weighted_f1

            # 添加稳定性扰动
            param_hash = hash(str(sorted(params.items()))) % 10000
            stability_term = param_hash * 1e-6
            current_loss += stability_term

            # 详细的性能信息日志输出
            logger.info(f"📊 Step {step_counter:3d} | "
                        f"F1: {f1:.4f} | "
                        f"F2: {fbeta_2:.4f} | "
                        f"Recall: {recall:.4f} | "
                        f"Precision: {precision:.4f} | "
                        f"Loss: {current_loss:.6f}")

            # 每10步输出一次详细信息
            if step_counter % 10 == 0:
                # 计算额外的评估指标用于对比
                balanced_acc = balanced_accuracy_score(y_val, y_val_pred)
                geometric_mean = geometric_mean_score(y_val, y_val_pred)

                # 过拟合检测：验证集与测试集性能差异
                test_f1 = test_metrics.get('test_f1', 0.0)
                test_recall = test_metrics.get('test_recall', 0.0)
                test_precision = test_metrics.get('test_precision', 0.0)

                # 计算验证集和测试集的性能差异
                f1_gap = abs(f1 - test_f1)
                recall_gap = abs(recall - test_recall)
                precision_gap = abs(precision - test_precision)

                # 完美分数检测 - 可能的过拟合或数据泄漏信号
                is_perfect_score = (f1 == 1.0 and recall == 1.0 and precision == 1.0)
                is_suspicious = (f1 > 0.99 or recall > 0.99 or precision > 0.99)

                logger.info(f"🔍 详细分析 Step {step_counter}:")
                logger.info(f"   - 验证集指标: F1={f1:.4f}, F2={fbeta_2:.4f}, Recall={recall:.4f}, Precision={precision:.4f}")
                logger.info(f"   - 平衡指标: Balanced_Acc={balanced_acc:.4f}, G-Mean={geometric_mean:.4f}")
                logger.info(f"   - 测试集指标: F1={test_f1:.4f}, Recall={test_recall:.4f}, Precision={test_precision:.4f}")
                logger.info(f"   - 性能差异: F1_gap={f1_gap:.4f}, Recall_gap={recall_gap:.4f}, Precision_gap={precision_gap:.4f}")
                logger.info(f"   - 数据分布: 异常比例={positive_ratio:.4f}")
                logger.info(f"   - 当前损失: {current_loss:.6f} (基于F-beta score)")

                # 过拟合警告
                if is_perfect_score:
                    logger.warning(f"🚨 检测到完美分数 - 可能存在严重过拟合或数据泄漏!")
                    logger.warning(f"   建议检查:")
                    logger.warning(f"   1. 特征工程是否引入了未来信息")
                    logger.warning(f"   2. 数据集划分是否正确")
                    logger.warning(f"   3. 模型复杂度是否过高")
                    logger.warning(f"   4. 标签生成逻辑是否正确")
                elif is_suspicious:
                    logger.warning(f"⚠️  检测到异常高分 - 请检查是否过拟合")

                # 验证集与测试集差异过大警告
                if f1_gap > 0.2 or recall_gap > 0.2 or precision_gap > 0.2:
                    logger.warning(f"⚠️  验证集与测试集性能差异过大 - 可能过拟合")
                    logger.warning(f"   F1差异: {f1_gap:.4f}, 召回率差异: {recall_gap:.4f}, 精确率差异: {precision_gap:.4f}")

                # 数据分布合理性检查
                if positive_ratio > 0.8 or positive_ratio < 0.05:
                    logger.warning(f"⚠️  数据集标签分布异常: 异常比例={positive_ratio:.4f}")
                    if positive_ratio > 0.8:
                        logger.warning(f"   异常样本过多，可能不是真实的异常检测场景")
                    else:
                        logger.warning(f"   异常样本过少，可能导致模型学习困难")

            # 更新最佳模型
            if current_loss < best_loss:
                improvement = best_loss - current_loss
                best_loss = current_loss
                best_model = model
                logger.info(f"🎯 发现更好的模型! Step {step_counter}")
                logger.info(f"   ✨ 新最佳Loss: {current_loss:.6f} (改进: {improvement:.6f})")
                logger.info(f"   ✨ 验证集表现: F1={f1:.4f}, F2={fbeta_2:.4f}, Recall={recall:.4f}, Precision={precision:.4f}")
                logger.info(f"   ✨ 测试集表现: F1={test_metrics.get('test_f1', 0.0):.4f}, "
                            f"Recall={test_metrics.get('test_recall', 0.0):.4f}, "
                            f"Precision={test_metrics.get('test_precision', 0.0):.4f}")

                # 显示当前最佳模型的参数
                param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
                logger.info(f"   🔧 模型参数: {param_str}")

            # 性能警告
            if fbeta_2 < 0.1 and step_counter > 5:
                logger.warning(f"⚠️  F-beta性能较差 (F2={fbeta_2:.4f}) - 可能需要调整超参数")

            if recall < 0.1 and step_counter > 5:
                logger.warning(f"⚠️  召回率过低 (Recall={recall:.4f}) - 异常检测漏检严重")

            # 记录详细的优化信息
            mlflow.log_metric("optimization_loss", current_loss, step=step_counter)
            mlflow.log_metric("fbeta_2", fbeta_2, step=step_counter)
            mlflow.log_metric("balanced_accuracy", balanced_accuracy_score(y_val, y_val_pred), step=step_counter)
            mlflow.log_metric("geometric_mean", geometric_mean_score(y_val, y_val_pred), step=step_counter)
            mlflow.log_metric("positive_ratio", positive_ratio, step=step_counter)

            # 记录验证集指标（用于优化）
            mlflow.log_metric("val_f1", f1, step=step_counter)
            mlflow.log_metric("val_recall", recall, step=step_counter)
            mlflow.log_metric("val_precision", precision, step=step_counter)
            mlflow.log_metric("val_accuracy", val_accuracy, step=step_counter)

            # 记录测试集指标（仅监控，不用于优化决策）
            mlflow.log_metric("test_f1", test_metrics.get(
                'test_f1', 0.0), step=step_counter)
            mlflow.log_metric("test_recall", test_metrics.get(
                'test_recall', 0.0), step=step_counter)
            mlflow.log_metric("test_precision", test_metrics.get(
                'test_precision', 0.0), step=step_counter)
            mlflow.log_metric("test_accuracy", test_accuracy,
                              step=step_counter)

            return {"loss": current_loss, "status": STATUS_OK, "model": model, "val_f1": f1}

        with mlflow.start_run() as run:
            # 记录优化策略信息
            mlflow.log_param("optimization_strategy", "enhanced_multi_objective_anomaly_detection")
            mlflow.log_param("recall_priority", True)
            mlflow.log_param("imbalance_aware", True)
            mlflow.log_param("loss_design_version", "v2_enhanced_discrimination")

            # 记录数据集统计信息
            train_positive_ratio = np.mean(y_train)
            val_positive_ratio = np.mean(y_val)
            test_positive_ratio = np.mean(y_test)

            mlflow.log_param("train_positive_ratio", train_positive_ratio)
            mlflow.log_param("val_positive_ratio", val_positive_ratio)
            mlflow.log_param("test_positive_ratio", test_positive_ratio)

            logger.info(f"🚀 开始超参数优化 - 最大评估次数: {entity.max_evals}")
            logger.info(f"📊 数据集统计:")
            logger.info(f"   - 训练集: {len(X_train)} 样本, 异常比例: {train_positive_ratio:.4f}")
            logger.info(f"   - 验证集: {len(X_val)} 样本, 异常比例: {val_positive_ratio:.4f}")
            logger.info(f"   - 测试集: {len(X_test)} 样本, 异常比例: {test_positive_ratio:.4f}")
            logger.info(f"🎯 优化目标: 召回率优先的多目标优化 (Loss设计版本: v2)")

            fmin(
                fn=objective,
                space=hyperopt_config,
                algo=tpe.suggest,
                max_evals=entity.max_evals,
                trials=trials,
                verbose=True
            )

            # 确保最佳模型存在
            if best_model is None:
                logger.error("❌ 未找到有效的最佳模型")
                raise ValueError("训练过程中未能产生有效模型")

            # 为最佳模型添加必要属性
            best_model.window = entity.windows_size
            best_model.freq = freq

            # 最终测试集评估
            y_test_pred_final = best_model.predict(X_test)
            final_test_metrics = self.calculate_metrics(
                y_test, y_test_pred_final, subprefix='final_test')

            # 计算最终验证集F1分数用于记录
            y_val_pred_final = best_model.predict(X_val)
            final_val_metrics = self.calculate_metrics(
                y_val, y_val_pred_final, subprefix='final_val')
            val_f1 = final_val_metrics.get('final_val_f1', 0.0)

            # 输出最终训练结果总结
            logger.info(f"🏆 训练完成! 最终结果总结:")
            logger.info(f"   💎 最佳Loss: {best_loss:.6f}")
            logger.info(f"   📈 验证集最终表现:")
            logger.info(f"      - F1 Score: {val_f1:.4f}")
            logger.info(f"      - Recall: {final_val_metrics.get('final_val_recall', 0.0):.4f}")
            logger.info(f"      - Precision: {final_val_metrics.get('final_val_precision', 0.0):.4f}")
            logger.info(f"   📊 测试集最终表现:")
            logger.info(f"      - F1 Score: {final_test_metrics.get('final_test_f1', 0.0):.4f}")
            logger.info(f"      - Recall: {final_test_metrics.get('final_test_recall', 0.0):.4f}")
            logger.info(f"      - Precision: {final_test_metrics.get('final_test_precision', 0.0):.4f}")

            # 性能评估建议
            final_f1 = final_test_metrics.get('final_test_f1', 0.0)
            final_recall = final_test_metrics.get('final_test_recall', 0.0)
            final_precision = final_test_metrics.get('final_test_precision', 0.0)

            if final_f1 >= 0.8:
                logger.info(f"✅ 模型性能优秀 (F1={final_f1:.4f})")
            elif final_f1 >= 0.6:
                logger.info(f"✅ 模型性能良好 (F1={final_f1:.4f})")
            elif final_f1 >= 0.4:
                logger.info(f"⚠️  模型性能一般 (F1={final_f1:.4f}) - 建议调优")
            else:
                logger.warning(f"❌ 模型性能较差 (F1={final_f1:.4f}) - 需要重新设计")

            if final_recall < 0.5:
                logger.warning(f"⚠️  召回率偏低 (Recall={final_recall:.4f}) - 可能存在漏检风险")

            if final_precision < 0.3:
                logger.warning(f"⚠️  精确率偏低 (Precision={final_precision:.4f}) - 误报率较高")

            # 记录最终指标到MLflow
            for metric_name, metric_value in final_test_metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            for metric_name, metric_value in final_val_metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            # 记录模型配置参数
            mlflow.log_param("windows_size", entity.windows_size)
            mlflow.log_param("feature_count", len(feature_columns))
            mlflow.log_param("frequency", freq)
            mlflow.log_param("train_samples", len(X_train))
            mlflow.log_param("val_samples", len(X_val))
            mlflow.log_param("test_samples", len(X_test))

            # 获取最佳参数并记录
            best_trial = min(trials.trials, key=lambda x: x['result']['loss'])
            best_params = best_trial['misc']['vals']

            # 解析最佳参数（处理hyperopt的参数格式）
            for param_name, param_values in best_params.items():
                if param_values:  # 非空列表
                    param_value = param_values[0]  # hyperopt将参数存储为列表
                    mlflow.log_param(f"best_{param_name}", param_value)

            # 注册模型到MLflow模型注册表
            model_name = f"{entity.algorithm}_{entity.id}"
            logger.info(f"📦 正在注册模型到MLflow: {model_name}")

            # 注册sklearn模型
            registered_model = mlflow.sklearn.log_model(
                sk_model=best_model,
                registered_model_name=model_name,
                input_example=pd.DataFrame(
                    X_train,
                    columns=feature_columns
                ).head(1)
            )

            # 获取注册后的模型版本信息
            logger.info(f"✅ 模型注册成功!")
            logger.info(f"   📋 模型名称: {model_name}")
            logger.info(f"   📊 最终性能: F1={final_f1:.4f}, Recall={final_recall:.4f}, Precision={final_precision:.4f}")
