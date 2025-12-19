"""Gradient Boosting 时间序列预测模型

使用 sklearn 的 GradientBoostingRegressor 进行时间序列预测。
通过滑动窗口特征工程将时间序列问题转换为监督学习问题。
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

from .base import BaseTimeSeriesModel, ModelRegistry
from .gradient_boosting_wrapper import GradientBoostingWrapper


@ModelRegistry.register("gradient_boosting")
class GradientBoostingModel(BaseTimeSeriesModel):
    """Gradient Boosting 时间序列预测模型
    
    使用滑动窗口方法将时间序列转换为监督学习问题：
    - lag_features: 使用过去N个时间步作为特征
    - 支持多步预测
    - 适合非线性、复杂模式的时间序列
    
    参数说明：
    - lag_features: 滞后特征数量（默认12）
    - n_estimators: 树的数量（默认100）
    - learning_rate: 学习率（默认0.1）
    - max_depth: 树的最大深度（默认3）
    - min_samples_split: 分裂所需的最小样本数（默认2）
    - min_samples_leaf: 叶子节点最小样本数（默认1）
    - subsample: 子采样比例（默认1.0）
    """
    
    def __init__(self,
                 lag_features: int = 12,
                 n_estimators: int = 100,
                 learning_rate: float = 0.1,
                 max_depth: int = 3,
                 min_samples_split: int = 2,
                 min_samples_leaf: int = 1,
                 subsample: float = 1.0,
                 random_state: int = 42,
                 use_feature_engineering: bool = True,
                 **kwargs):
        """初始化 Gradient Boosting 模型
        
        Args:
            lag_features: 滞后特征数量
            n_estimators: 树的数量
            learning_rate: 学习率
            max_depth: 树的最大深度
            min_samples_split: 分裂所需的最小样本数
            min_samples_leaf: 叶子节点最小样本数
            subsample: 子采样比例
            random_state: 随机种子
            use_feature_engineering: 是否使用完整的特征工程（推荐）
            **kwargs: 其他参数
        """
        super().__init__(
            lag_features=lag_features,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            subsample=subsample,
            random_state=random_state,
            use_feature_engineering=use_feature_engineering,
            **kwargs
        )
        
        self.lag_features = lag_features
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_samples_leaf = min_samples_leaf
        self.subsample = subsample
        self.random_state = random_state
        self.use_feature_engineering = use_feature_engineering
        
        # 用于预测的最后观测值
        self.last_train_values = None
        
        # 特征工程器
        self.feature_engineer = None
        
        # 特征名称（用于预测时转换为DataFrame）
        self.feature_names_ = None
        
        logger.debug(
            f"GradientBoosting 模型初始化: lag={self.lag_features}, "
            f"n_estimators={self.n_estimators}, lr={self.learning_rate}, "
            f"use_feature_engineering={self.use_feature_engineering}"
        )
    
    
    def _create_supervised_data(self, data: pd.Series) -> tuple:
        """将时间序列转换为监督学习数据
        
        Args:
            data: 时间序列数据
            
        Returns:
            (X, y): 特征矩阵和目标向量
        """
        values = data.values
        X, y = [], []
        
        for i in range(self.lag_features, len(values)):
            X.append(values[i - self.lag_features:i])
            y.append(values[i])
        
        return np.array(X), np.array(y)
    
    def fit(self,
            train_data: pd.Series,
            val_data: Optional[pd.Series] = None,
            merge_val: bool = True,
            **kwargs) -> 'GradientBoostingModel':
        """训练 Gradient Boosting 模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选）
            merge_val: 是否合并验证数据进行训练（默认 True）
                      **使用场景说明：**
                      - True（默认）: 合并 train+val 训练
                        * 用于最终训练阶段（Trainer 的 final training）
                        * 目的：最大化历史数据，提升预测能力
                        * 无需额外验证集评估
                      
                      - False: 仅用 train 训练，val 用于评估
                        * 用于超参数优化阶段（Hyperopt 的 objective 函数）
                        * 目的：在独立验证集上评估泛化能力，避免过拟合
                        * val 数据用于计算优化目标 loss
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确或数据量不足
        """
        # 根据 merge_val 决定是否合并验证数据
        if merge_val and val_data is not None:
            combined_data = pd.concat([train_data, val_data])
            logger.info("训练模式: 合并训练集和验证集")
        else:
            combined_data = train_data
            if val_data is not None:
                logger.info("训练模式: 仅使用训练集（验证集用于评估）")
            else:
                logger.info("训练模式: 仅使用训练集（无验证集）")
        
        if not isinstance(combined_data, pd.Series):
            raise ValueError("train_data 必须是 pandas.Series")
        
        logger.info(
            f"开始训练 GradientBoosting 模型: "
            f"n_estimators={self.n_estimators}, lr={self.learning_rate}"
        )
        logger.info(f"训练数据: {len(combined_data)} 个数据点")
        
        # 存储频率信息
        if isinstance(combined_data.index, pd.DatetimeIndex):
            try:
                self.frequency = pd.infer_freq(combined_data.index)
            except:
                self.frequency = None
        
        # 选择特征工程策略
        if self.use_feature_engineering:
            # 使用完整的特征工程
            from ..preprocessing.feature_engineering import TimeSeriesFeatureEngineer
            
            logger.info("使用完整的特征工程...")
            self.feature_engineer = TimeSeriesFeatureEngineer(
                lag_periods=list(range(1, self.lag_features + 1)),
                rolling_windows=[7, 14, 30] if self.lag_features >= 30 else [self.lag_features // 2],
                rolling_features=['mean', 'std', 'min', 'max'],
                use_temporal_features=True,
                use_cyclical_features=False,  # 避免过多特征
                use_diff_features=True,
                diff_periods=[1],
                drop_na=True
            )
            
            X_train, y_train = self.feature_engineer.fit_transform(combined_data)
            logger.info(f"特征工程后样本: X={X_train.shape}, y={y_train.shape}")
            logger.info(f"生成 {len(self.feature_engineer.get_feature_names())} 个特征")
            
            # 保存特征名称
            self.feature_names_ = X_train.columns.tolist()
            
            # 记录特征工程信息到MLflow（使用 metric 避免 hyperopt 冲突）
            if mlflow.active_run():
                try:
                    mlflow.log_param("feature_engineering_enabled", True)
                except:
                    pass  # 如果已存在则跳过
                
                # 使用 metric 记录可变参数（支持多次记录）
                mlflow.log_metric("model/n_features", X_train.shape[1])
                mlflow.log_metric("model/lag_features", self.lag_features)
                
                # 只在非 hyperopt 时保存详细信息
                if not merge_val or val_data is None:  # hyperopt 模式
                    pass  # 跳过详细记录
                else:  # 最终训练模式
                    try:
                        mlflow.log_param("feature_lag_periods", str(list(range(1, self.lag_features + 1))))
                        mlflow.log_param("feature_rolling_windows", str([7, 14, 30] if self.lag_features >= 30 else [self.lag_features // 2]))
                        mlflow.log_param("feature_use_temporal", True)
                        mlflow.log_param("feature_use_diff", True)
                        
                        # 记录前20个特征名称（避免过长）
                        feature_names_sample = self.feature_names_[:20]
                        mlflow.log_param("feature_names_sample", str(feature_names_sample))
                        
                        # 将完整特征列表保存为artifact
                        mlflow.log_text("\n".join(self.feature_names_), "features/feature_names.txt")
                    except:
                        pass  # 忽略重复记录错误
                
                logger.info(f"特征工程信息已记录到MLflow: {X_train.shape[1]} 个特征")
        else:
            # 使用简单的滞后窗口
            logger.info(f"使用简单滞后窗口: lag={self.lag_features}")
            X_train, y_train = self._create_supervised_data(train_data)
            logger.info(f"监督学习样本: X={X_train.shape}, y={y_train.shape}")
            
            # 记录简单模式信息到MLflow
            if mlflow.active_run():
                try:
                    mlflow.log_param("feature_engineering_enabled", False)
                    mlflow.log_param("feature_type", "simple_lag")
                except:
                    pass  # 如果已存在则跳过
                
                # 使用 metric 记录可变参数
                mlflow.log_metric("model/n_features", X_train.shape[1])
                mlflow.log_metric("model/lag_features", self.lag_features)
                
                logger.info(f"简单滞后特征信息已记录到MLflow: {X_train.shape[1]} 个特征")
        
        # 创建并训练模型
        try:
            self.model = GradientBoostingRegressor(
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                min_samples_leaf=self.min_samples_leaf,
                subsample=self.subsample,
                random_state=self.random_state,
                verbose=0
            )
            
            self.model.fit(X_train, y_train)
            logger.info("模型训练完成")
            
            # 保存最后的观测值用于预测
            self.last_train_values = train_data.values[-max(self.lag_features, 50):].copy()
            self.last_train_data = combined_data.copy()  # 保存实际训练数据用于预测和评估
            
            self.is_fitted = True
            
            # 记录特征重要性
            feature_importance = self.model.feature_importances_
            logger.debug(f"特征重要性: {feature_importance[:5]}... (前5个)")
            
            return self
            
        except Exception as e:
            logger.error(f"GradientBoosting 模型训练失败: {e}")
            raise
    
    def predict(self, steps: int) -> np.ndarray:
        """预测未来N步
        
        使用递归预测策略：每次预测一步，然后将预测值加入窗口继续预测。
        
        Args:
            steps: 预测步数
            
        Returns:
            预测结果数组
            
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()
        
        if steps <= 0:
            raise ValueError(f"预测步数必须大于0，当前值: {steps}")
        
        logger.debug(f"预测未来 {steps} 步")
        
        if self.use_feature_engineering and self.feature_engineer:
            # 使用特征工程的递归预测
            logger.info(f"使用特征工程的递归预测")
            return self._predict_with_feature_engineering(steps)
        else:
            # 使用简单滞后窗口的递归预测
            logger.info(f"使用简单滞后窗口的递归预测")
            return self._predict_simple(steps)
    
    def _predict_simple(self, steps: int) -> np.ndarray:
        """简单滞后窗口预测"""
        predictions = []
        current_window = self.last_train_values.copy()
        
        for i in range(steps):
            X = current_window[-self.lag_features:].reshape(1, -1)
            pred = self.model.predict(X)[0]
            predictions.append(pred)
            current_window = np.append(current_window[1:], pred)
        
        return np.array(predictions)
    
    def _predict_with_feature_engineering(self, steps: int) -> np.ndarray:
        """使用特征工程的递归预测
        
        策略：维护完整的时间序列历史，每步预测后追加到历史，
        重新调用feature_engineer.transform()提取特征。
        
        优点：
        - 特征提取逻辑完全一致，不会出错
        - 支持任意复杂的特征工程（时间特征、周期特征等）
        - 代码简洁，易于维护
        
        性能考虑：
        - 每步都调用transform有开销
        - 但对于月度数据，预测步数通常不多（12-36步），可接受
        - 正确性 >> 性能
        """
        if not hasattr(self, 'last_train_data') or self.last_train_data is None:
            raise RuntimeError("last_train_data 未初始化，无法进行预测")
        
        # 维护完整的历史序列（包含DatetimeIndex）
        history = self.last_train_data.copy()
        predictions = []
        
        for step in range(steps):
            # 1. 从完整历史中提取特征
            try:
                X, _ = self.feature_engineer.transform(history)
            except Exception as e:
                logger.error(f"特征提取失败: {e}")
                logger.warning("回退到简单预测方法")
                return self._predict_simple(steps - step)
            
            if len(X) == 0:
                logger.warning(f"第 {step+1} 步特征提取结果为空，停止预测")
                break
            
            # 2. 使用最后一行特征进行预测
            last_features = X.iloc[-1:].copy()
            pred = self.model.predict(last_features)[0]
            predictions.append(pred)
            
            # 3. 推断下一个时间步（基于频率）
            last_timestamp = history.index[-1]
            if isinstance(history.index, pd.DatetimeIndex):
                # 尝试推断频率
                freq = history.index.freq
                if freq is None:
                    try:
                        freq = pd.infer_freq(history.index[-12:])  # 用最近12个点推断
                    except:
                        freq = None
                
                if freq:
                    next_timestamp = last_timestamp + pd.tseries.frequencies.to_offset(freq)
                else:
                    # 回退：使用平均间隔
                    avg_delta = (history.index[-1] - history.index[-2])
                    next_timestamp = last_timestamp + avg_delta
            else:
                # 非时间索引，简单递增
                next_timestamp = last_timestamp + 1
            
            # 4. 将预测值追加到历史（构造新的Series）
            new_point = pd.Series([pred], index=[next_timestamp])
            history = pd.concat([history, new_point])
        
        return np.array(predictions)
    
    def _infer_frequency(self, index: pd.DatetimeIndex) -> Optional[str]:
        """推断时间序列频率
        
        Args:
            index: 时间索引
            
        Returns:
            频率字符串(如'MS', 'D')或None
        """
        try:
            return pd.infer_freq(index)
        except Exception:
            return None
    
    def _threshold_from_frequency(self, freq: str) -> int:
        """根据频率返回保守的预测步数阈值
        
        策略:避免长期预测导致误差累积
        - 月度: 24步 (2年)
        - 周度: 26步 (半年)
        - 日度: 90步 (1季度)
        - 小时/分钟: 168步 (1周)
        
        Args:
            freq: pandas频率字符串
            
        Returns:
            推荐的最大预测步数
        """
        freq_upper = freq.upper() if freq else ''
        
        # 月度频率
        if any(x in freq_upper for x in ['M', 'Q', 'Y']):
            return 24
        # 周度频率
        elif 'W' in freq_upper:
            return 26
        # 日度频率
        elif 'D' in freq_upper or 'B' in freq_upper:
            return 90
        # 小时/分钟频率
        elif any(x in freq_upper for x in ['H', 'T', 'MIN']):
            return 168
        # 默认保守值
        else:
            return 36
    
    def _get_default_warn_threshold(self, test_data: pd.Series) -> int:
        """获取默认的预测步数警告阈值
        
        优先级:
        1. 如果是DatetimeIndex且能推断频率 -> 使用频率自适应阈值(80-90%情况)
        2. 否则 -> 使用数据长度自适应阈值(保守策略)
        
        Args:
            test_data: 测试数据
            
        Returns:
            警告阈值
        """
        # 尝试从时间索引推断频率
        if isinstance(test_data.index, pd.DatetimeIndex):
            freq = self._infer_frequency(test_data.index)
            if freq:
                threshold = self._threshold_from_frequency(freq)
                logger.debug(f"推断频率: {freq}, 使用阈值: {threshold}")
                return threshold
        
        # 回退:基于数据长度的保守阈值
        # 取 max(6, min(length//10, 36))
        length = len(test_data)
        threshold = max(6, min(length // 10, 36))
        logger.debug(f"无法推断频率,使用数据长度自适应阈值: {threshold} (数据长度: {length})")
        return threshold
    
    def _evaluate_rolling(
        self,
        test_data: pd.Series,
        horizon: int,
        verbose: bool = True
    ) -> tuple:
        """滚动预测评估
        
        策略:模拟生产环境的滚动预测过程
        - 每次只预测horizon步
        - 使用真实值更新历史窗口
        - 避免长期递归导致的误差累积
        - 关键:直接使用test_data的时间索引,无需推断
        
        Args:
            test_data: 测试数据
            horizon: 单次预测步数
            verbose: 是否输出详细日志
            
        Returns:
            (predictions, y_true) 元组
        """
        if horizon <= 0:
            raise ValueError(f"horizon必须大于0,当前值: {horizon}")
        
        predictions = []
        y_true = []
        n_samples = len(test_data)
        
        # 维护训练历史
        if self.use_feature_engineering and self.feature_engineer:
            # 特征工程模式:维护完整的历史序列(包含DatetimeIndex)
            if not hasattr(self, 'last_train_data') or self.last_train_data is None:
                raise RuntimeError("last_train_data未初始化,无法进行滚动预测")
            history = self.last_train_data.copy()
        else:
            # 简单模式:维护滞后窗口
            history_values = self.last_train_values.copy()
        
        # 滚动预测循环
        i = 0
        while i < n_samples:
            # 计算本轮预测步数
            steps_to_predict = min(horizon, n_samples - i)
            
            # 获取本轮的目标切片(包含时间戳和真实值)
            target_slice = test_data.iloc[i:i+steps_to_predict]
            
            # 执行预测
            if self.use_feature_engineering and self.feature_engineer:
                # 特征工程模式:逐步预测,使用test_data的时间戳
                preds = []
                for timestamp, true_value in target_slice.items():
                    # 提取特征
                    try:
                        X, _ = self.feature_engineer.transform(history)
                    except Exception as e:
                        logger.error(f"特征提取失败: {e}")
                        # 回退到简单预测
                        remaining = steps_to_predict - len(preds)
                        simple_preds = self._predict_simple(remaining)
                        preds.extend(simple_preds)
                        break
                    
                    if len(X) == 0:
                        logger.warning(f"特征提取结果为空,停止预测")
                        break
                    
                    # 使用最后一行特征进行预测
                    last_features = X.iloc[-1:].copy()
                    pred = self.model.predict(last_features)[0]
                    preds.append(pred)
                    
                    # 使用test_data的时间戳追加真实值
                    new_point = pd.Series([true_value], index=[timestamp])
                    history = pd.concat([history, new_point])
            else:
                # 简单模式:使用滞后窗口的递归预测
                preds = self._predict_simple_rolling(
                    history_values, steps_to_predict
                )
                # 用真实值更新滞后窗口
                true_values = target_slice.values
                history_values = np.append(history_values, true_values)
                if len(history_values) > len(self.last_train_values):
                    history_values = history_values[-len(self.last_train_values):]
            
            # 收集预测结果
            predictions.extend(preds)
            
            # 收集真实值
            y_true.extend(target_slice.values)
            
            i += steps_to_predict
            
            if verbose and (i % (horizon * 5) == 0 or i == n_samples):
                logger.info(f"滚动预测进度: {i}/{n_samples} ({i/n_samples*100:.1f}%)")
        
        return np.array(predictions), np.array(y_true)
    
    def _predict_simple_rolling(self, history_values: np.ndarray, steps: int) -> np.ndarray:
        """简单滞后窗口的滚动预测辅助方法"""
        predictions = []
        current_window = history_values.copy()
        
        for _ in range(steps):
            X = current_window[-self.lag_features:].reshape(1, -1)
            pred = self.model.predict(X)[0]
            predictions.append(pred)
            # 注意:这里是滚动预测,但在单轮horizon内仍是递归
            current_window = np.append(current_window[1:], pred)
        
        return np.array(predictions)
    
    def evaluate(
        self,
        test_data: pd.Series,
        mode: str = 'auto',
        horizon: Optional[int] = None,
        warn_threshold: Optional[int] = None,
        is_in_sample: bool = False,
        verbose: bool = True
    ) -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据(带 DatetimeIndex 的 Series)
            mode: 预测模式
                - 'auto': 自动选择(根据步数和阈值智能切换)
                - 'recursive': 递归预测(使用预测值生成新预测)
                - 'rolling': 滚动预测(使用真实值更新历史)
            horizon: 滚动预测的单次预测步数(仅mode='rolling'时使用)
            warn_threshold: 长期预测警告阈值(None=自动推断)
            is_in_sample: 评估模式选择器（优先级高于 mode）
                **参数语义说明：**
                - False（默认）: 样本外评估（Out-of-sample evaluation）
                  * 用于验证集/测试集评估
                  * 从训练集末尾开始预测未来 N 步
                  * 模拟真实生产场景，评估泛化能力
                  * 可能有递归误差累积（根据 mode 选择策略缓解）
                
                - True: 样本内评估（In-sample evaluation）
                  * 用于训练集评估（Hyperopt 中检测欠拟合）
                  * 从数据本身重新提取特征进行预测
                  * 避免递归预测的误差累积
                  * 准确反映模型对已见数据的拟合能力
                  * 速度更快（无需逐步预测）
                
                **使用场景：**
                - Hyperopt objective: 
                  * `evaluate(train_data, is_in_sample=True)` → 检测欠拟合
                  * `evaluate(val_data, is_in_sample=False)` → 检测过拟合
                - Trainer 训练后: 
                  * `evaluate(train+val, is_in_sample=True)` → 检查拟合度
                - Trainer 测试集: 
                  * `evaluate(test_data, is_in_sample=False)` → 评估泛化能力
            verbose: 是否输出详细日志
            
        Returns:
            评估指标字典 {"rmse": ..., "mae": ..., "mape": ..., "_predictions": ..., "_y_true": ...}
            注意: 以下划线开头的键为内部数据，供 Trainer 使用
            
        Raises:
            RuntimeError: 模型未训练
            ValueError: mode='rolling'时未提供horizon
        """
        self._check_fitted()
        
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series")
        
        steps = len(test_data)
        
        # 1. 样本内评估优先级最高(兼容旧代码)
        if is_in_sample:
            if verbose:
                logger.info(f"使用样本内评估模式 (快速特征重构)")
            # 样本内评估:直接用数据重构特征进行预测(快速)
            if self.use_feature_engineering and self.feature_engineer:
                X, y_true = self.feature_engineer.transform(test_data)
                if len(X) == 0:
                    raise ValueError("特征提取失败,无法进行样本内评估")
                predictions = self.model.predict(X)
            else:
                X, y_true = self._create_supervised_data(test_data)
                predictions = self.model.predict(X)
        
        # 2. 模式选择逻辑
        else:
            # 获取警告阈值
            if warn_threshold is None:
                warn_threshold = self._get_default_warn_threshold(test_data)
            
            # 决定实际使用的模式
            if mode == 'auto':
                # 自动模式:根据步数选择
                if steps > warn_threshold:
                    actual_mode = 'rolling'
                    if horizon is None:
                        horizon = max(1, warn_threshold // 2)  # 默认使用阈值的一半
                    if verbose:
                        logger.warning(
                            f"测试集长度({steps})超过阈值({warn_threshold}), "
                            f"自动切换到滚动预测模式(horizon={horizon})"
                        )
                else:
                    actual_mode = 'recursive'
                    if verbose:
                        logger.info(f"测试集长度({steps})在阈值内, 使用递归预测模式")
            else:
                actual_mode = mode
                if verbose:
                    logger.info(f"使用指定的预测模式: {actual_mode}")
            
            # 根据模式执行预测
            if actual_mode == 'rolling':
                if horizon is None:
                    raise ValueError("mode='rolling'时必须提供horizon参数")
                predictions, y_true = self._evaluate_rolling(test_data, horizon, verbose)
            else:  # recursive
                if steps > warn_threshold and verbose:
                    logger.warning(
                        f"递归预测 {steps} 步超过建议阈值 {warn_threshold}, "
                        f"可能导致误差累积。建议使用 mode='rolling' 或 mode='auto'"
                    )
                predictions = self.predict(steps)
                y_true = test_data.values
        
        # 计算指标
        metrics = self._calculate_metrics(y_true, predictions)
        
        # 计算预测偏差（系统性误差）
        prediction_bias = float((predictions - y_true).mean())
        prediction_bias_pct = float(prediction_bias / y_true.mean() * 100) if y_true.mean() != 0 else 0.0
        
        metrics['prediction_bias'] = prediction_bias
        metrics['prediction_bias_pct'] = prediction_bias_pct
        
        # 添加内部数据供 Trainer 使用（下划线前缀表示内部数据）
        metrics['_predictions'] = predictions
        metrics['_y_true'] = y_true
        if not is_in_sample and 'actual_mode' in locals():
            metrics['_mode'] = actual_mode
        
        logger.info(
            f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
            f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%, "
            f"Bias={prediction_bias:.4f} ({prediction_bias_pct:+.2f}%)"
        )
        
        return metrics
    
    def evaluate_with_plot(
        self,
        train_data: pd.Series,
        test_data: pd.Series,
        plot_residuals: bool = True
    ) -> Dict[str, float]:
        """评估模型性能并绘制可视化图表
        
        Args:
            train_data: 训练数据（用于绘图对比）
            test_data: 测试数据（带 DatetimeIndex 的 Series）
            plot_residuals: 是否绘制残差分析图
            
        Returns:
            评估指标字典
        """
        self._check_fitted()
        
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series")
        
        # 预测
        steps = len(test_data)
        predictions = self.predict(steps)
        
        # 计算指标
        y_true = test_data.values
        metrics = self._calculate_metrics(y_true, predictions)
        
        logger.info(
            f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
            f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%"
        )
        
        # 绘制预测结果图
        if mlflow.active_run():
            from ..mlflow_utils import MLFlowUtils
            
            # 1. 预测结果对比图
            MLFlowUtils.plot_prediction_results(
                train_data=train_data,
                test_data=test_data,
                predictions=predictions,
                title=f"GradientBoosting 预测结果 (lag={self.lag_features})",
                artifact_name="gb_prediction",
                metrics=metrics
            )
            
            # 2. 残差分析图
            if plot_residuals:
                residuals = y_true - predictions
                MLFlowUtils.plot_residuals_analysis(
                    residuals=residuals,
                    title="GradientBoosting 残差分析",
                    artifact_name="gb_residuals"
                )
            
            # 3. 特征重要性图
            self._plot_feature_importance()
            
            logger.info("预测可视化图表已上传到 MLflow")
        
        return metrics
    
    def _plot_feature_importance(self):
        """绘制特征重要性"""
        if not self.is_fitted or self.model is None:
            return
        
        import matplotlib.pyplot as plt
        
        importance = self.model.feature_importances_
        indices = np.argsort(importance)[::-1]
        
        # 只显示Top 20特征，避免图表过于拥挤
        n_show = min(20, len(importance))
        top_indices = indices[:n_show]
        top_importance = importance[top_indices]
        
        # 获取特征名称
        if self.feature_names_:
            feature_labels = [self.feature_names_[i] for i in top_indices]
        else:
            feature_labels = [f"t-{self.lag_features-i}" for i in top_indices]
        
        # 绘图
        plt.figure(figsize=(12, 8))
        plt.title(f"特征重要性 Top {n_show} (总特征数: {len(importance)})")
        plt.barh(range(n_show), top_importance)
        plt.yticks(range(n_show), feature_labels, fontsize=8)
        plt.xlabel("重要性")
        plt.ylabel("特征")
        plt.gca().invert_yaxis()  # 最重要的在上面
        plt.tight_layout()
        
        if mlflow.active_run():
            mlflow.log_figure(plt.gcf(), "gb_feature_importance.png")
            
            # 记录Top 10特征及其重要性
            top10_dict = {feature_labels[i]: float(top_importance[i]) for i in range(min(10, n_show))}
            for feat, imp in top10_dict.items():
                mlflow.log_metric(f"importance_{feat}", imp)
            
            logger.debug(f"Top 10 特征重要性: {list(top10_dict.keys())}")
        
        plt.close()
    
    def get_params(self) -> Dict[str, Any]:
        """获取模型参数"""
        return {
            'lag_features': self.lag_features,
            'n_estimators': self.n_estimators,
            'learning_rate': self.learning_rate,
            'max_depth': self.max_depth,
            'min_samples_split': self.min_samples_split,
            'min_samples_leaf': self.min_samples_leaf,
            'subsample': self.subsample,
            'random_state': self.random_state
        }
    
    def optimize_hyperparams(
        self,
        train_data: pd.Series,
        val_data: pd.Series,
        config: Any
    ) -> Dict[str, Any]:
        """优化 Gradient Boosting 超参数
        
        使用 Hyperopt 进行贝叶斯优化。
        
        Args:
            train_data: 训练数据
            val_data: 验证数据
            config: 训练配置对象（包含搜索空间和优化设置）
            
        Returns:
            最优超参数字典
        """
        from hyperopt import fmin, tpe, hp, Trials, STATUS_OK
        
        max_evals = config.hyperopt_max_evals
        metric = config.hyperopt_metric
        search_space_config = config.get("hyperparams", "gradient_boosting", "search", "search_space")
        
        # 获取早停配置
        early_stop_config = config.get("hyperparams", "gradient_boosting", "search", "early_stopping")
        early_stop_enabled = early_stop_config.get("enabled", False) if early_stop_config else False
        patience = early_stop_config.get("patience", 15) if early_stop_config else 15
        
        # 异常值配置
        loss_cap_multiplier = early_stop_config.get("loss_cap_multiplier", 5.0) if early_stop_config else 5.0
        
        logger.info(
            f"开始超参数优化: max_evals={max_evals}, metric={metric}"
        )
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")
        
        # 计算动态上限值（用于截断异常 loss）
        data_std = train_data.std()
        cap_value = data_std * loss_cap_multiplier
        logger.info(
            f"Loss 上限阈值: {cap_value:.2f} "
            f"(std {data_std:.2f} × {loss_cap_multiplier})"
        )
        
        # 定义搜索空间
        space = self._build_search_space(search_space_config)
        
        # 优化状态跟踪
        trials = Trials()
        best_score = [float('inf')]
        eval_count = [0]
        failed_count = [0]
        
        def objective(params):
            eval_count[0] += 1
            current_eval = eval_count[0]
            
            try:
                logger.info("=" * 60)
                logger.info(f"Hyperopt Trial [{current_eval}/{max_evals}]")
                logger.info(f"  hyperopt 采样的原始参数: {params}")
                for key, value in params.items():
                    logger.info(f"    {key}: {value} (type: {type(value).__name__})")
                logger.info("=" * 60)
                
                # 准备参数（hyperopt 直接返回实际值）
                decoded_params = self._decode_params(params, search_space_config)
                
                logger.info(f"  解码后的参数: {decoded_params}")
                logger.info("=" * 60)
                
                # 创建临时模型并训练（仅用 train_data，val_data 用于评估）
                temp_model = GradientBoostingModel(**decoded_params)
                temp_model.fit(train_data, val_data=val_data, merge_val=False)
                
                # 训练集评估（样本内评估，快速检测欠拟合）
                train_metrics = temp_model.evaluate(train_data, is_in_sample=True)
                train_score = train_metrics.get(metric, train_metrics['rmse'])
                
                # 验证集评估（样本外预测，检测过拟合）
                val_metrics = temp_model.evaluate(val_data, is_in_sample=False)
                val_score = val_metrics.get(metric, val_metrics['rmse'])
                score = val_score  # 用验证集 loss 进行优化
                
                # 异常值提前返回
                if score > cap_value:
                    failed_count[0] += 1
                    logger.debug(
                        f"  [{current_eval}/{max_evals}] ⚠ 异常 loss "
                        f"({score:.2f} > {cap_value:.2f})，返回惩罚值"
                    )
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.2, step=current_eval)
                        mlflow.log_param(f"trial_{current_eval}_anomaly_value", f"{score:.2e}")
                        mlflow.log_metric("hyperopt/success", 0.5, step=current_eval)
                    
                    return {'loss': float(cap_value * 1.5), 'status': STATUS_OK}
                
                # 正常值：记录到 MLflow
                if mlflow.active_run():
                    # 记录训练集指标
                    mlflow.log_metric(f"hyperopt/train_{metric}", train_score, step=current_eval)
                    mlflow.log_metric("hyperopt/train_rmse", train_metrics['rmse'], step=current_eval)
                    mlflow.log_metric("hyperopt/train_mae", train_metrics['mae'], step=current_eval)
                    mlflow.log_metric("hyperopt/train_mape", train_metrics['mape'], step=current_eval)
                    
                    # 记录验证集指标
                    mlflow.log_metric(f"hyperopt/val_{metric}", val_score, step=current_eval)
                    mlflow.log_metric("hyperopt/val_rmse", val_metrics['rmse'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_mae", val_metrics['mae'], step=current_eval)
                    mlflow.log_metric("hyperopt/val_mape", val_metrics['mape'], step=current_eval)
                    
                    # 记录过拟合指标（val_loss - train_loss）
                    overfit_gap = val_score - train_score
                    mlflow.log_metric("hyperopt/overfit_gap", overfit_gap, step=current_eval)
                    
                    mlflow.log_metric("hyperopt/success", 1.0, step=current_eval)
                    
                    # 记录本次 trial 的详细参数
                    for key, value in decoded_params.items():
                        mlflow.log_param(f"trial_{current_eval}_{key}", value)
                
                # 记录最优结果
                if score < best_score[0]:
                    improvement_pct = 0.0
                    if best_score[0] != float('inf'):
                        improvement_pct = (best_score[0] - score) / best_score[0] * 100
                    
                    best_score[0] = score
                    
                    logger.info(
                        f"  ✓ 发现更优参数! [{current_eval}/{max_evals}] "
                        f"{metric}={score:.4f}"
                    )
                    logger.info(f"    参数: {decoded_params}")
                    
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", score, step=current_eval)
                        if improvement_pct > 0:
                            mlflow.log_metric("hyperopt/improvement_pct", improvement_pct, step=current_eval)
                
                return {'loss': float(score), 'status': STATUS_OK}
                
            except Exception as e:
                failed_count[0] += 1
                logger.error(
                    f"  [{current_eval}/{max_evals}] 参数评估失败: {type(e).__name__}: {str(e)}"
                )
                
                if mlflow.active_run():
                    mlflow.log_metric("hyperopt/loss_anomaly", cap_value * 1.5, step=current_eval)
                    mlflow.log_metric("hyperopt/success", 0.0, step=current_eval)
                    error_msg = str(e)[:150]
                    mlflow.log_param(f"trial_{current_eval}_error", error_msg)
                
                return {'loss': float('inf'), 'status': STATUS_OK}
        
        # 运行优化
        from hyperopt.early_stop import no_progress_loss
        from hyperopt import space_eval
        
        best_params_raw = fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(None),
            verbose=False
        )
        
        logger.info("=" * 60)
        logger.info("Hyperopt 优化完成，转换最优参数...")
        logger.info(f"  fmin() 返回的原始值（索引）: {best_params_raw}")
        
        # 使用 space_eval 将索引转换为实际值（标准做法）
        best_params_actual = space_eval(space, best_params_raw)
        logger.info(f"  space_eval() 转换后的实际值: {best_params_actual}")
        logger.info("=" * 60)
        
        # 转换最优参数（添加默认值和类型转换）
        best_params = self._decode_params(best_params_actual, search_space_config)
        
        logger.info(f"超参数优化完成! 最优{metric}: {best_score[0]:.4f}")
        logger.info(f"最优参数: {best_params}")
        
        # 记录优化摘要统计到 MLflow
        if mlflow.active_run():
            success_losses = [
                t['result']['loss'] for t in trials.trials 
                if t['result']['status'] == 'ok' and t['result']['loss'] != float('inf')
            ]
            
            success_count = len(success_losses)
            actual_evals = len(trials.trials)
            is_early_stopped = actual_evals < max_evals
            
            summary_metrics = {
                "hyperopt_summary/total_evals": max_evals,
                "hyperopt_summary/actual_evals": actual_evals,
                "hyperopt_summary/successful_evals": success_count,
                "hyperopt_summary/failed_evals": failed_count[0],
                "hyperopt_summary/success_rate": (success_count / actual_evals * 100) if actual_evals > 0 else 0,
                "hyperopt_summary/best_loss": best_score[0],
            }
            
            if early_stop_enabled:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 1.0
                summary_metrics["hyperopt_summary/early_stopped"] = 1.0 if is_early_stopped else 0.0
                summary_metrics["hyperopt_summary/patience_used"] = patience
                
                if is_early_stopped:
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    summary_metrics["hyperopt_summary/time_saved_pct"] = time_saved_pct
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )
            else:
                summary_metrics["hyperopt_summary/early_stop_enabled"] = 0.0
            
            if success_losses:
                summary_metrics.update({
                    "hyperopt_summary/worst_loss": max(success_losses),
                    "hyperopt_summary/mean_loss": np.mean(success_losses),
                    "hyperopt_summary/median_loss": np.median(success_losses),
                    "hyperopt_summary/std_loss": np.std(success_losses),
                })
                
                first_success_loss = success_losses[0] if success_losses else best_score[0]
                if first_success_loss > 0 and best_score[0] < first_success_loss:
                    improvement_pct = (first_success_loss - best_score[0]) / first_success_loss * 100
                    summary_metrics["hyperopt_summary/improvement_pct"] = improvement_pct
            
            mlflow.log_metrics(summary_metrics)
            logger.info(
                f"优化摘要: 成功率 {summary_metrics['hyperopt_summary/success_rate']:.1f}% "
                f"({success_count}/{actual_evals})"
            )
        
        # 更新当前模型参数
        for key, value in best_params.items():
            setattr(self, key, value)
        self.config.update(best_params)
        
        return best_params
    
    def _build_search_space(self, search_space_config: Dict) -> Dict:
        """构建 Hyperopt 搜索空间
        
        Args:
            search_space_config: 搜索空间配置
            
        Returns:
            Hyperopt 搜索空间字典
        """
        from hyperopt import hp
        
        if not search_space_config:
            # 默认搜索空间
            return {
                'n_estimators': hp.choice('n_estimators', [50, 100, 200, 300]),
                'learning_rate': hp.choice('learning_rate', [0.01, 0.05, 0.1, 0.2]),
                'max_depth': hp.choice('max_depth', [3, 5, 7, 10]),
                'min_samples_split': hp.choice('min_samples_split', [2, 5, 10]),
                'min_samples_leaf': hp.choice('min_samples_leaf', [1, 2, 4]),
                'subsample': hp.choice('subsample', [0.7, 0.8, 0.9, 1.0]),
                'lag_features': hp.choice('lag_features', [6, 12, 18, 24]),
            }
        
        # 从配置构建搜索空间
        space = {}
        
        if 'n_estimators' in search_space_config:
            space['n_estimators'] = hp.choice('n_estimators', search_space_config['n_estimators'])
        
        if 'learning_rate' in search_space_config:
            space['learning_rate'] = hp.choice('learning_rate', search_space_config['learning_rate'])
        
        if 'max_depth' in search_space_config:
            space['max_depth'] = hp.choice('max_depth', search_space_config['max_depth'])
        
        if 'min_samples_split' in search_space_config:
            space['min_samples_split'] = hp.choice('min_samples_split', search_space_config['min_samples_split'])
        
        if 'min_samples_leaf' in search_space_config:
            space['min_samples_leaf'] = hp.choice('min_samples_leaf', search_space_config['min_samples_leaf'])
        
        if 'subsample' in search_space_config:
            space['subsample'] = hp.choice('subsample', search_space_config['subsample'])
        
        if 'lag_features' in search_space_config:
            space['lag_features'] = hp.choice('lag_features', search_space_config['lag_features'])
        
        return space
    
    def _decode_params(self, params_raw: Dict, search_space_config: Dict) -> Dict:
        """准备模型参数
        
        Args:
            params_raw: Hyperopt 返回的参数（经过 space_eval 转换后的实际值）
            search_space_config: 搜索空间配置（未使用，保留接口兼容性）
            
        Returns:
            模型参数字典
        """
        # 1. 转换 numpy 类型为 Python 原生类型
        decoded = {}
        for key, value in params_raw.items():
            if isinstance(value, np.integer):
                decoded[key] = int(value)
            elif isinstance(value, np.floating):
                decoded[key] = float(value)
            else:
                decoded[key] = value
        
        # 2. 添加固定参数
        decoded['random_state'] = self.random_state
        decoded['use_feature_engineering'] = self.use_feature_engineering
        
        # 3. 参数验证和修正（防御性编程）
        if 'min_samples_split' in decoded:
            if decoded['min_samples_split'] < 2:
                logger.warning(
                    f"min_samples_split={decoded['min_samples_split']} < 2，"
                    f"已修正为 2"
                )
                decoded['min_samples_split'] = 2
        
        if 'min_samples_leaf' in decoded:
            if decoded['min_samples_leaf'] < 1:
                logger.warning(
                    f"min_samples_leaf={decoded['min_samples_leaf']} < 1，"
                    f"已修正为 1"
                )
                decoded['min_samples_leaf'] = 1
        
        if 'subsample' in decoded:
            if decoded['subsample'] > 1.0:
                logger.warning(
                    f"subsample={decoded['subsample']} > 1.0，已修正为 1.0"
                )
                decoded['subsample'] = 1.0
            elif decoded['subsample'] <= 0.0:
                logger.warning(
                    f"subsample={decoded['subsample']} <= 0.0，已修正为 0.8"
                )
                decoded['subsample'] = 0.8
        
        if 'learning_rate' in decoded:
            if decoded['learning_rate'] <= 0.0:
                logger.warning(
                    f"learning_rate={decoded['learning_rate']} <= 0.0，"
                    f"已修正为 0.1"
                )
                decoded['learning_rate'] = 0.1
        
        return decoded
    
    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        Args:
            artifact_path: MLflow artifact 路径
            
        Raises:
            RuntimeError: 模型未训练
            Exception: 模型序列化失败
        """
        self._check_fitted()
        
        logger.info("=" * 60)
        logger.info("开始保存模型到 MLflow")
        logger.info(f"artifact_path: {artifact_path}")
        logger.info(f"use_feature_engineering: {self.use_feature_engineering}")
        logger.info(f"last_train_data 长度: {len(self.last_train_data)}")
        logger.info(f"feature_engineer: {type(self.feature_engineer) if self.feature_engineer else None}")
        logger.info("=" * 60)
        
        # 记录模型元数据
        if mlflow.active_run():
            import sklearn
            try:
                import feature_engine
                fe_version = feature_engine.__version__
            except:
                fe_version = "unknown"
            
            metadata = {
                'model_type': 'gradient_boosting',
                'lag_features': self.lag_features,
                'use_feature_engineering': self.use_feature_engineering,
                'n_features': len(self.feature_names_) if self.feature_names_ else self.lag_features,
                'frequency': self.frequency,
                'data_length': len(self.last_train_data),
                'sklearn_version': sklearn.__version__,
                'feature_engine_version': fe_version,
            }
            
            try:
                mlflow.log_dict(metadata, "model_metadata.json")
                logger.info("✓ 元数据已记录")
            except Exception as e:
                logger.warning(f"元数据记录失败: {e}")
        
        # 测试 feature_engineer 可序列化性
        if self.use_feature_engineering and self.feature_engineer:
            logger.info("测试 feature_engineer 序列化...")
            try:
                import cloudpickle
                serialized = cloudpickle.dumps(self.feature_engineer)
                logger.info(f"✓ feature_engineer 序列化成功，大小: {len(serialized)} bytes")
                # 测试反序列化
                deserialized = cloudpickle.loads(serialized)
                logger.info(f"✓ feature_engineer 反序列化成功: {type(deserialized)}")
            except Exception as e:
                logger.error(f"✗ feature_engineer 序列化测试失败: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"详细错误:\n{traceback.format_exc()}")
                raise RuntimeError(f"feature_engineer 不可序列化: {e}")
        
        # 创建 Wrapper（stateless 设计，只保存训练频率）
        logger.info("创建 GradientBoostingWrapper...")
        wrapped_model = GradientBoostingWrapper(
            model=self.model,
            lag_features=self.lag_features,
            use_feature_engineering=self.use_feature_engineering,
            feature_engineer=self.feature_engineer if self.use_feature_engineering else None,
            training_frequency=self.frequency,
            feature_names=self.feature_names_
        )
        logger.info("✓ Wrapper 创建成功")
        
        # 测试 Wrapper 序列化
        logger.info("测试 Wrapper 序列化...")
        try:
            import cloudpickle
            serialized = cloudpickle.dumps(wrapped_model)
            logger.info(f"✓ Wrapper 序列化成功，大小: {len(serialized)} bytes")
        except Exception as e:
            logger.error(f"✗ Wrapper 序列化测试失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            raise RuntimeError(f"Wrapper 不可序列化: {e}")
        
        # 保存模型
        logger.info("调用 mlflow.pyfunc.log_model()...")
        try:
            mlflow.pyfunc.log_model(
                artifact_path=artifact_path,
                python_model=wrapped_model,
                signature=None  # 设置为 None，支持灵活的字典输入
            )
            logger.info(f"✓ mlflow.pyfunc.log_model() 调用完成")
            
            # 验证模型是否真的保存了
            if mlflow.active_run():
                run_id = mlflow.active_run().info.run_id
                logger.info(f"验证模型文件是否存在 (Run ID: {run_id})...")
                try:
                    # 尝试列出 artifacts
                    client = mlflow.tracking.MlflowClient()
                    artifacts = client.list_artifacts(run_id, artifact_path)
                    if artifacts:
                        logger.info(f"✓ 发现 {len(artifacts)} 个 artifact 文件:")
                        for art in artifacts[:5]:  # 只显示前5个
                            logger.info(f"  - {art.path}")
                    else:
                        logger.error(f"✗ artifact path '{artifact_path}' 下没有文件！")
                        raise RuntimeError(f"模型保存失败：artifact path '{artifact_path}' 为空")
                except Exception as e:
                    logger.warning(f"无法验证 artifacts: {e}")
            
            logger.info(f"✓ 模型已保存到 MLflow: {artifact_path}")
            logger.info("=" * 60)
        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"✗ 模型保存失败: {type(e).__name__}: {e}")
            logger.error("可能原因:")
            logger.error("  1. feature_engineer 包含不可序列化的对象")
            logger.error("  2. feature-engine 库版本不兼容")
            logger.error("  3. 内存不足或磁盘空间不足")
            logger.error(f"调试信息: use_feature_engineering={self.use_feature_engineering}")
            if self.feature_engineer:
                logger.error(f"  feature_engineer 类型: {type(self.feature_engineer)}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            logger.error("=" * 60)
            raise
