"""使用 sktime 封装的 Prophet 模型适配器。

此模块直接依赖 sktime 中的 fbprophet 封装：
`from sktime.forecasting.fbprophet import Prophet`。
提供 fit/predict/evaluate 接口，兼容项目中 Trainer 的调用方式。
"""

from typing import Any, Dict, Optional
import pandas as pd
import numpy as np
from loguru import logger
import mlflow

from .base import BaseTimeSeriesModel, ModelRegistry
from sktime.forecasting.fbprophet import Prophet as SKProphet
@ModelRegistry.register("Prophet")
class ProphetModel(BaseTimeSeriesModel):
    """Prophet 模型（优先 sktime 封装，回退到直接 prophet）"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._backend = 'sktime'
        self.model = None

        # 允许传入的 Prophet 构造参数白名单（基于 sktime.forecasting.fbprophet.Prophet 官方签名）
        # 参考: https://www.sktime.net/en/stable/api_reference/auto_generated/sktime.forecasting.fbprophet.Prophet.html
        allowed = {
            # === 用户常配置参数（应该出现在配置文件） ===
            'growth',                      # 增长模式: 'linear'（默认）| 'logistic' | 'flat'
            'seasonality_mode',            # 季节性模式: 'additive'（默认）| 'multiplicative'
            'seasonality_prior_scale',     # 季节性强度先验尺度（默认 10.0）
            'holidays_prior_scale',        # 节假日效应强度（默认 10.0）
            'changepoint_prior_scale',     # 趋势变点灵活度（默认 0.05，最重要的超参数）
            'n_changepoints',              # 潜在变点数量（默认 25）
            'yearly_seasonality',          # 年度季节性: 'auto' | True | False | int
            'weekly_seasonality',          # 周季节性: 'auto' | True | False | int
            'daily_seasonality',           # 日季节性: 'auto' | True | False | int
            
            # === 高级/可选参数（白名单支持但不推荐用户直接配置） ===
            'changepoint_range',           # 变点范围比例（默认 0.8，不建议修改）
            'changepoints',                # 手动指定变点位置（高级用法，需传入日期列表）
            'growth_floor',                # logistic 增长的下限（仅 growth='logistic' 时使用）
            'growth_cap',                  # logistic 增长的上限（仅 growth='logistic' 时使用）
            'holidays',                    # 自定义节假日 DataFrame（高级用法）
            'add_seasonality',             # 添加自定义季节性（高级用法，需字典配置）
            'add_country_holidays',        # 添加国家节假日（如 'US', 'CN'）
            
            # === 内部/调试参数（白名单支持但不应暴露给用户） ===
            'mcmc_samples',                # MCMC 采样数（默认 0，使用 MAP；>0 时训练极慢）
            'alpha',                       # 不确定性区间显著性水平（默认 0.05）
            'uncertainty_samples',         # 不确定性区间采样数（默认 1000）
            'stan_backend',                # Stan 后端配置（None 或 'CMDSTANPY'）
            'verbose',                     # 日志详细程度（0=静默，1=基本，2=详细）
            'freq'                         # 时间序列频率（通常自动推断，如 'D', 'MS'）
        }

        # 过滤掉 trainer 可能传入但不属于 Prophet 的参数
        self.prophet_params = {k: v for k, v in kwargs.items() if k in allowed}
        
        # 应用数据频率自适应的默认参数（如果未指定）
        self._apply_smart_defaults()

        # 保留原始 kwargs 以供超参优化基准使用
        self._raw_kwargs = dict(kwargs)

        self.SKProphet = SKProphet
        logger.debug(f"Prophet 模型初始化: {self.prophet_params}")
    
    def _apply_smart_defaults(self):
        """应用数据频率自适应的默认参数
        
        根据经验和 Prophet 文档，为关键参数设置合理默认值：
        - changepoint_prior_scale: 趋势灵活度（默认 0.05 过于保守）
        - seasonality_prior_scale: 季节性强度
        - seasonality_mode: 加性 vs 乘性
        """
        # changepoint_prior_scale: Prophet 最重要的超参数
        # 默认 0.05 适合平稳数据，但对于有明显趋势变化的数据过于保守
        # 提升到 0.1-0.15 可以更好地捕捉趋势变化
        if 'changepoint_prior_scale' not in self.prophet_params:
            self.prophet_params['changepoint_prior_scale'] = 0.1
            logger.debug("应用默认 changepoint_prior_scale=0.1 (原默认 0.05)")
        
        # seasonality_prior_scale: 控制季节性拟合强度
        # 默认 10.0 适合大多数情况
        if 'seasonality_prior_scale' not in self.prophet_params:
            self.prophet_params['seasonality_prior_scale'] = 10.0
        
        # seasonality_mode: 加性 vs 乘性
        # 默认 'additive' 适合季节性幅度固定的数据
        # 'multiplicative' 适合季节性幅度随趋势变化的数据（如销售额）
        if 'seasonality_mode' not in self.prophet_params:
            self.prophet_params['seasonality_mode'] = 'additive'
    
    def _get_default_search_space(self) -> Dict[str, Any]:
        """获取 Prophet 的默认超参数搜索空间
        
        基于 Prophet 文档和经验，为关键超参数提供合理的搜索范围。
        
        关键超参数说明：
        - changepoint_prior_scale: 趋势变点灵活度（最重要）
          * 小值（0.001-0.05）: 趋势平滑，适合稳定数据
          * 中值（0.05-0.5）: 平衡，适合大多数数据
          * 大值（0.5-10）: 趋势灵活，适合频繁变化的数据
        
        - seasonality_prior_scale: 季节性强度
          * 小值（0.01-1）: 季节性弱
          * 中值（1-10）: 季节性中等（默认 10）
          * 大值（10-100）: 季节性强
        
        - seasonality_mode: 加性 vs 乘性
          * 'additive': 季节性幅度固定
          * 'multiplicative': 季节性幅度随趋势变化
        
        Returns:
            搜索空间配置字典
        """
        return {
            # 最重要的超参数：趋势灵活度
            'changepoint_prior_scale': {
                'type': 'loguniform',
                'low': -4.0,  # exp(-4) ≈ 0.018
                'high': 1.0   # exp(1) ≈ 2.718
            },
            
            # 季节性强度
            'seasonality_prior_scale': {
                'type': 'loguniform',
                'low': -2.0,  # exp(-2) ≈ 0.135
                'high': 3.0   # exp(3) ≈ 20.09
            },
            
            # 季节性模式
            'seasonality_mode': {
                'type': 'choice',
                'options': ['additive', 'multiplicative']
            },
            
            # 变点数量（可选）
            'n_changepoints': {
                'type': 'choice',
                'options': [15, 25, 35, 50]
            }
        }
    
    def _build_hyperopt_space(self, search_space_conf: Dict[str, Any]) -> Dict:
        """构建 hyperopt 搜索空间
        
        支持多种参数类型：
        - list: 离散选择 (hp.choice)
        - dict with 'type': 根据类型构建
          * 'choice': hp.choice
          * 'uniform': hp.uniform
          * 'loguniform': hp.loguniform
          * 'quniform': hp.quniform
        
        Args:
            search_space_conf: 搜索空间配置字典
            
        Returns:
            hyperopt 搜索空间字典
        """
        from hyperopt import hp
        
        space = {}
        
        for param_name, param_config in search_space_conf.items():
            try:
                # 简单列表格式 -> hp.choice
                if isinstance(param_config, list) and len(param_config) > 0:
                    space[param_name] = hp.choice(param_name, param_config)
                    logger.debug(f"参数 {param_name}: choice({param_config})")
                
                # 字典格式 -> 根据 type 构建
                elif isinstance(param_config, dict) and 'type' in param_config:
                    param_type = param_config['type']
                    
                    if param_type == 'choice':
                        options = param_config.get('options', [])
                        if len(options) > 0:
                            space[param_name] = hp.choice(param_name, options)
                            logger.debug(f"参数 {param_name}: choice({options})")
                    
                    elif param_type == 'uniform':
                        low = param_config.get('low', 0.0)
                        high = param_config.get('high', 1.0)
                        space[param_name] = hp.uniform(param_name, low, high)
                        logger.debug(f"参数 {param_name}: uniform({low}, {high})")
                    
                    elif param_type == 'loguniform':
                        low = param_config.get('low', -2.0)
                        high = param_config.get('high', 2.0)
                        space[param_name] = hp.loguniform(param_name, low, high)
                        logger.debug(f"参数 {param_name}: loguniform({low}, {high})")
                    
                    elif param_type == 'quniform':
                        low = param_config.get('low', 0.0)
                        high = param_config.get('high', 1.0)
                        q = param_config.get('q', 1.0)
                        space[param_name] = hp.quniform(param_name, low, high, q)
                        logger.debug(f"参数 {param_name}: quniform({low}, {high}, {q})")
                    
                    else:
                        logger.warning(f"不支持的参数类型: {param_name}: {param_type}")
                
                else:
                    logger.warning(f"跳过不支持的参数格式: {param_name}: {param_config}")
            
            except Exception as e:
                logger.warning(f"构建参数 {param_name} 的搜索空间失败: {e}")
        
        return space

    def fit(self, 
            train_data: pd.Series, 
            val_data: Optional[pd.Series] = None,
            merge_val: bool = True,
            verbose: bool = True,
            **kwargs) -> 'ProphetModel':
        """训练 Prophet 模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选）
            merge_val: 是否合并验证数据进行训练（默认 True）
                      - True（默认）: 合并 train+val 训练，用于最终训练
                      - False: 仅用 train 训练，val 用于超参优化评估
            verbose: 是否输出详细训练日志（默认 True）
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
        """
        # 根据 merge_val 决定是否合并验证数据
        if merge_val and val_data is not None:
            combined_data = pd.concat([train_data, val_data])
            if verbose:
                logger.info("训练模式: 合并训练集和验证集")
        else:
            combined_data = train_data
            if val_data is not None:
                if verbose:
                    logger.info("训练模式: 仅使用训练集（验证集用于评估）")
            else:
                if verbose:
                    logger.info("训练模式: 仅使用训练集（无验证集）")
        
        if not isinstance(combined_data, pd.Series):
            raise ValueError("train_data 必须是 pandas.Series 且包含 DatetimeIndex")
        
        # 确保时间索引单调递增（sktime要求）
        if not combined_data.index.is_monotonic_increasing:
            if verbose:
                logger.warning("检测到时间索引乱序，正在排序...")
            combined_data = combined_data.sort_index()
            if verbose:
                logger.info(f"排序后数据范围: {combined_data.index[0]} 到 {combined_data.index[-1]}")

        if verbose:
            logger.info(f"训练数据: {len(combined_data)} 个数据点")
            
            # 超长序列警告（业界标准：Prophet适合中等长度序列）
            if len(combined_data) > 500:
                years = len(combined_data) / 12  # 假设月度数据
                logger.warning(
                    f"⚠️  训练数据非常长（{len(combined_data)}个月 ≈ {years:.1f}年）。\n"
                    f"   Prophet设计用于中等长度序列（通常<500个点）。\n"
                    f"   超长序列可能导致：1) 训练速度慢  2) 预测精度下降  3) 数值稳定性问题\n"
                    f"   建议：1) 只使用最近几年数据  2) 考虑ARIMA/LSTM等模型\n"
                    f"   当前仍将使用全部数据训练，但请关注训练时间和预测质量。"
                )
        
        # sktime 的封装通常接受 y: pd.Series
        self.model = self.SKProphet(**self.prophet_params)
        self.model.fit(combined_data)

        self.is_fitted = True
        self.last_train_data = combined_data.copy()
        
        # 推断频率（sktime 需要用于 ForecastingHorizon）
        try:
            self.frequency = pd.infer_freq(combined_data.index)
            # 如果推断失败，尝试从 index.freq 获取
            if self.frequency is None and hasattr(combined_data.index, 'freq'):
                self.frequency = combined_data.index.freq
            # 如果还是 None，尝试手动计算
            if self.frequency is None and len(combined_data.index) >= 3:
                # 计算时间间隔的众数作为频率
                deltas = pd.Series(combined_data.index[1:]) - pd.Series(combined_data.index[:-1])
                mode_delta = deltas.mode()[0] if len(deltas.mode()) > 0 else deltas.iloc[0]
                self.frequency = pd.tseries.frequencies.to_offset(mode_delta)
        except Exception as e:
            logger.warning(f"频率推断失败: {e}，将使用月度频率 'MS' 作为默认值")
            self.frequency = 'MS'  # 默认使用月初频率
        
        if verbose:
            logger.info(f"Prophet 模型训练完成，frequency={self.frequency}")
        
        return self

    def predict(self, steps: int) -> np.ndarray:
        self._check_fitted()
        if steps <= 0:
            raise ValueError("steps 必须大于 0")
        
        # 调试日志（仅在短期预测时输出，避免长期预测日志刷屏）
        is_short_term = steps <= 50  # 50步以内视为短期预测
        if is_short_term:
            logger.debug(f"predict调用: steps={steps}, backend={self._backend}, frequency={self.frequency}")

        try:
            if self._backend == 'sktime':
                from sktime.forecasting.base import ForecastingHorizon
                
                # 安全地创建预测范围（避免 int64 溢出）
                try:
                    # 限制最大预测步数以避免溢出
                    safe_steps = min(steps, 10000)  # 最多预测 10000 步
                    if steps > safe_steps:
                        logger.warning(f"预测步数 {steps} 过大，限制为 {safe_steps}")
                        steps = safe_steps
                    
                    if is_short_term:
                        logger.debug(f"创建ForecastingHorizon: steps={steps}, freq={self.frequency}")
                    # 创建预测范围（CRITICAL: 必须提供 freq 参数）
                    fh = ForecastingHorizon(range(1, steps + 1), is_relative=True, freq=self.frequency)
                    if is_short_term:
                        logger.debug(f"调用model.predict(fh)")
                    y_pred = self.model.predict(fh)
                    if is_short_term:
                        logger.debug(f"预测完成，结果类型: {type(y_pred)}, 长度: {len(y_pred) if hasattr(y_pred, '__len__') else 'N/A'}")
                except OverflowError as e:
                    logger.error(f"创建预测范围溢出: {e}，尝试使用较小步数")
                    # 回退：使用更小的步数（但仍然尝试预测尽可能多）
                    fallback_steps = min(steps, 500)  # 回退到500步
                    logger.info(f"回退到 {fallback_steps} 步预测")
                    fh = ForecastingHorizon(range(1, fallback_steps + 1), is_relative=True, freq=self.frequency)
                    y_pred = self.model.predict(fh)
                    
                    # 如果请求的步数更多，用最后一个值填充（简单策略）
                    if fallback_steps < steps:
                        last_value = y_pred.values[-1] if isinstance(y_pred, pd.Series) else y_pred[-1]
                        additional = np.full(steps - fallback_steps, last_value)
                        
                        if isinstance(y_pred, pd.Series):
                            y_pred_array = y_pred.values
                        elif isinstance(y_pred, pd.DataFrame):
                            y_pred_array = y_pred.iloc[:, 0].values
                        else:
                            y_pred_array = np.asarray(y_pred)
                        
                        y_pred = np.concatenate([y_pred_array, additional])
                        logger.warning(f"预测结果从 {fallback_steps} 补齐到 {steps} 步（使用最后值填充）")
                        return y_pred
                
                # sktime 返回 pd.Series 或 pd.DataFrame
                if isinstance(y_pred, pd.Series):
                    return y_pred.values
                elif isinstance(y_pred, pd.DataFrame):
                    # 取第一列
                    return y_pred.iloc[:, 0].values
                else:
                    return np.asarray(y_pred)
            else:
                # direct prophet
                logger.debug(f"使用direct prophet预测，frequency={self.frequency}")
                if self.frequency is not None:
                    future = self.model.make_future_dataframe(periods=steps, freq=self.frequency)
                else:
                    future = self.model.make_future_dataframe(periods=steps)
                fcst = self.model.predict(future)
                if 'yhat' in fcst.columns:
                    return fcst['yhat'].values[-steps:]
                else:
                    return fcst.iloc[-steps:, 0].values
        except Exception as e:
            logger.error(f"Prophet 预测失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"详细堆栈:\n{traceback.format_exc()}")
            raise

    def _infer_frequency(self, index: pd.DatetimeIndex) -> Optional[str]:
        """推断时间序列频率
        
        Args:
            index: DatetimeIndex
            
        Returns:
            频率字符串（如 'MS', 'D', 'H'）或 None
        """
        try:
            return pd.infer_freq(index)
        except (ValueError, TypeError):
            return None
    
    def _threshold_from_frequency(self, freq: str) -> int:
        """根据频率返回保守的预测步数阈值
        
        策略:避免长期预测导致误差累积（与 GB 完全一致）
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
        
        优先级(与 GB 完全一致):
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
        """分段预测评估（不重新训练，符合业界标准）
        
        Prophet 业界标准做法：
        - 模型只训练一次（已在fit中完成）
        - 分段预测horizon步以缓解长期预测误差累积
        - 不插入真实值（Prophet API限制）
        - 接受渐进式误差累积（Prophet设计如此）
        
        注意：此方法用于长期预测评估（>阈值），不用于超参优化。
        超参优化使用样本内评估（is_in_sample=True），速度极快。
        
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
        n_samples = len(test_data)
        
        if verbose:
            logger.info(
                f"使用分段预测模式（horizon={horizon}），模型不重新训练。"
                f"注意：Prophet适合短中期预测，超长期预测精度可能下降。"
            )
        
        # 分段预测循环（不重新训练）
        i = 0
        round_num = 0
        while i < n_samples:
            round_num += 1
            steps_to_predict = min(horizon, n_samples - i)
            
            # 从训练末尾预测未来 i+steps 步，取后 steps 个
            # 注意：Prophet必须从训练末尾开始预测，无法跳过中间步骤
            total_steps = i + steps_to_predict
            
            try:
                all_preds = self.predict(total_steps)
                preds = all_preds[i:total_steps]
            except Exception as e:
                logger.error(f"第{round_num}轮预测失败（预测{total_steps}步）: {e}")
                # 回退：用前一轮的最后值填充
                if len(predictions) > 0:
                    preds = np.full(steps_to_predict, predictions[-1])
                else:
                    raise RuntimeError(f"首轮预测失败，无法继续: {e}")
            
            predictions.extend(preds)
            i += steps_to_predict
            
            if verbose and (i % (horizon * 5) == 0 or i == n_samples):
                logger.info(f"分段预测进度: {i}/{n_samples} ({i/n_samples*100:.1f}%)")
        
        y_true = test_data.values
        return np.array(predictions), y_true

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
                - 'recursive': 递归预测(一次性预测所有步数)
                - 'rolling': 滚动预测(分段预测,不重新训练)
            horizon: 滚动预测的单次预测步数(仅mode='rolling'时使用)
            warn_threshold: 长期预测警告阈值(None=自动推断)
            is_in_sample: 是否为样本内评估
                - False(默认): 样本外评估,从训练末尾预测未来
                - True: 样本内评估,返回训练期间的拟合值(fitted values)
            verbose: 是否输出详细日志
            
        Returns:
            评估指标字典 {"rmse": ..., "mae": ..., "mape": ..., "_predictions": ..., "_y_true": ...}
            注意: 以下划线开头的键为内部数据，供 Trainer 使用
            
        Raises:
            RuntimeError: 模型未训练
            ValueError: mode='rolling'时未提供horizon
            
        Note:
            - 样本内评估使用训练期拟合值,避免时间溢出
            - 样本外评估根据mode自动选择直接预测或滚动预测
            - Prophet滚动预测不重新训练(与GB/RF保持一致),只分段预测
        """
        self._check_fitted()
        if not isinstance(test_data, pd.Series):
            raise ValueError("test_data 必须是 pandas.Series 且包含 DatetimeIndex")

        # 样本内评估：只评估最后少量数据（Prophet特殊策略）
        if is_in_sample:
            # Prophet特殊性：无法插入真实值进行滚动预测（API限制）
            # 因此预测步数越多，误差累积越大，样本内评估指标会很差
            # 策略：只评估最后6-12步（根据频率自适应），既快速又能反映拟合质量
            
            # 获取推荐的短期预测步数（通常6-24步）
            if warn_threshold is None:
                default_threshold = self._get_default_warn_threshold(test_data)
            else:
                default_threshold = warn_threshold
            
            # 样本内评估窗口：取推荐阈值的1/2，最少6步，最多24步
            # 这样既能反映拟合质量，又避免长期预测误差累积
            eval_window = min(24, max(6, default_threshold // 2))
            eval_window = min(eval_window, len(test_data))
            eval_data = test_data.iloc[-eval_window:]
            
            if verbose:
                logger.info(
                    f"样本内评估（短期窗口）：评估最后 {eval_window}/{len(test_data)} 步。"
                    f"Prophet无法使用真实值滚动预测，短期窗口避免误差累积。"
                )
            
            # 一次性预测（从训练末尾预测未来eval_window步）
            try:
                preds = self.predict(eval_window)
                y_true = eval_data.values
            except Exception as e:
                logger.error(f"样本内评估预测失败: {e}")
                # 回退：使用最小窗口
                fallback_window = 6
                logger.warning(f"回退到最小评估窗口: {fallback_window}步")
                eval_data = test_data.iloc[-fallback_window:]
                preds = self.predict(fallback_window)
                y_true = eval_data.values
        
        # 样本外评估：根据预测长度选择策略（业界标准）
        else:
            steps = len(test_data)
            
            # 获取推荐预测阈值
            if warn_threshold is None:
                warn_threshold = self._get_default_warn_threshold(test_data)
            
            # 决定实际使用的模式
            if mode == 'auto':
                # 自动模式：根据步数智能选择
                if steps <= warn_threshold:
                    # 短期预测：直接预测（Prophet最佳使用场景）
                    actual_mode = 'direct'
                    if verbose:
                        logger.info(f"短期预测（{steps}步≤阈值{warn_threshold}），使用直接预测模式")
                else:
                    # 长期预测：警告用户 + 分段预测
                    actual_mode = 'rolling'
                    if horizon is None:
                        horizon = warn_threshold  # 使用阈值作为分段大小
                    if verbose:
                        logger.warning(
                            f"⚠️  长期预测警告：预测{steps}步超过推荐阈值{warn_threshold}。\n"
                            f"   Prophet设计用于短中期预测，长期预测精度可能显著下降。\n"
                            f"   建议：1) 缩短测试集长度  2) 使用ARIMA/LSTM等长期预测模型\n"
                            f"   当前策略：使用分段预测（horizon={horizon}）缓解误差累积。"
                        )
            elif mode == 'recursive':
                actual_mode = 'direct'
                if steps > warn_threshold and verbose:
                    logger.warning(
                        f"⚠️  直接预测{steps}步超过推荐阈值{warn_threshold}，精度可能下降。"
                    )
            elif mode == 'rolling':
                actual_mode = 'rolling'
                if horizon is None:
                    raise ValueError("mode='rolling'时必须提供horizon参数")
            else:
                raise ValueError(f"不支持的预测模式: {mode}")
            
            # 执行预测
            if actual_mode == 'rolling':
                preds, y_true = self._evaluate_rolling(test_data, horizon, verbose)
            else:  # direct
                preds = self.predict(steps)
                y_true = test_data.values
        
        # 计算指标
        metrics = self._calculate_metrics(y_true, preds)
        
        # 计算预测偏差（系统性误差）
        prediction_bias = float((preds - y_true).mean())
        prediction_bias_pct = float(prediction_bias / y_true.mean() * 100) if y_true.mean() != 0 else 0.0
        
        metrics['prediction_bias'] = prediction_bias
        metrics['prediction_bias_pct'] = prediction_bias_pct
        
        # 添加内部数据供 Trainer 使用（下划线前缀表示内部数据）
        metrics['_predictions'] = preds
        metrics['_y_true'] = y_true
        if not is_in_sample and 'actual_mode' in locals():
            metrics['_mode'] = actual_mode
        
        if verbose:
            logger.info(
                f"模型评估完成: RMSE={metrics['rmse']:.4f}, "
                f"MAE={metrics['mae']:.4f}, MAPE={metrics['mape']:.2f}%, "
                f"Bias={prediction_bias:.4f} ({prediction_bias_pct:+.2f}%)"
            )
        
        return metrics

    def optimize_hyperparams(self, train_data: pd.Series, val_data: pd.Series, config: Any) -> Dict[str, Any]:
        """使用 hyperopt 优化 Prophet 的超参数。

        从 config.get_search_config() 获取 search_space、max_evals、metric 等。
        返回最优参数字典（不包含 loss）。
        """
        from hyperopt import fmin, tpe, hp, Trials, STATUS_OK
        from hyperopt import space_eval
        from hyperopt.early_stop import no_progress_loss

        logger.info("开始 Prophet 超参数优化...")

        search_cfg = config.get_search_config()
        max_evals = search_cfg.get("max_evals", 20)
        metric = search_cfg.get("metric", "rmse")
        search_space_conf = search_cfg.get("search_space", {})
        early_cfg = search_cfg.get("early_stopping", {})
        
        # 早停配置（用于超参优化过程，非Prophet训练过程）
        early_stop_enabled = early_cfg.get("enabled", True)
        patience = early_cfg.get("patience", 10)  # 连续无改进的trial容忍次数
        
        if early_stop_enabled:
            logger.info(f"早停机制: 启用 (patience={patience})")

        # 构建 hyperopt 搜索空间
        # 如果配置文件未提供搜索空间，使用默认的 Prophet 搜索空间
        if not search_space_conf or len(search_space_conf) == 0:
            logger.info("未指定搜索空间，使用 Prophet 默认搜索空间")
            search_space_conf = self._get_default_search_space()
        
        space = self._build_hyperopt_space(search_space_conf)

        if len(space) == 0:
            logger.warning("未检测到可搜索的参数空间，跳过优化")
            return {}

        trials = Trials()
        best_score = [float('inf')]
        best_params = None
        eval_counter = {"n": 0}

        def objective(params):
            eval_counter["n"] += 1
            current = eval_counter["n"]

            # 合并基础参数与本次尝试参数（使用原始 kwargs 为基准以保留未过滤的默认）
            trial_params = {**self._raw_kwargs, **params}

            try:
                # 构建临时模型（会自动过滤非 Prophet 参数）
                temp = ProphetModel(**trial_params)
                
                # 输出当前尝试的 Prophet 有效参数（从模型实例获取已过滤的参数）
                logger.info(f"[{current}/{max_evals}] 尝试参数:")
                for k, v in temp.prophet_params.items():
                    logger.info(f"  {k}={v}")
                
                # 训练模型
                temp.fit(train_data, val_data=val_data, merge_val=False, verbose=False)

                # 训练集评估（样本内评估，检测欠拟合）
                train_metrics = temp.evaluate(train_data, is_in_sample=True)
                train_score = train_metrics.get(metric, train_metrics['rmse'])
                
                # 验证集评估（样本外预测，检测过拟合）
                val_metrics = temp.evaluate(val_data, is_in_sample=False)
                val_score = val_metrics.get(metric, val_metrics['rmse'])
                score = val_score  # 用验证集 loss 进行优化
                
                # 计算过拟合指标
                overfit_gap = val_score - train_score
                
                # 输出评估结果
                logger.info(
                    f"  train_{metric}={train_score:.4f}, "
                    f"val_{metric}={val_score:.4f}, "
                    f"gap={overfit_gap:+.4f}"
                )

                # MLflow 记录
                if mlflow.active_run():
                    # 记录训练集指标
                    mlflow.log_metric(f"hyperopt/train_{metric}", float(train_score), step=current)
                    mlflow.log_metric("hyperopt/train_rmse", float(train_metrics['rmse']), step=current)
                    mlflow.log_metric("hyperopt/train_mae", float(train_metrics['mae']), step=current)
                    mlflow.log_metric("hyperopt/train_mape", float(train_metrics['mape']), step=current)
                    
                    # 记录验证集指标
                    mlflow.log_metric(f"hyperopt/val_{metric}", float(val_score), step=current)
                    mlflow.log_metric("hyperopt/val_rmse", float(val_metrics['rmse']), step=current)
                    mlflow.log_metric("hyperopt/val_mae", float(val_metrics['mae']), step=current)
                    mlflow.log_metric("hyperopt/val_mape", float(val_metrics['mape']), step=current)
                    
                    # 记录过拟合指标
                    mlflow.log_metric("hyperopt/overfit_gap", float(overfit_gap), step=current)
                    
                    # 记录本次 trial 的详细参数
                    for k, v in params.items():
                        try:
                            mlflow.log_param(f"trial_{current}_{k}", str(v))
                        except Exception:
                            pass

                nonlocal best_score, best_params
                
                # 更新最优结果（Hyperopt 的 early_stop_fn 会自动处理早停）
                if score < best_score[0]:
                    best_score[0] = score
                    best_params = params.copy()
                    logger.info(f"  ✓ 新最优: {metric}={best_score[0]:.4f}")
                    if mlflow.active_run():
                        mlflow.log_metric("hyperopt/best_so_far", float(best_score[0]), step=current)

                return {"loss": float(score), "status": STATUS_OK}

            except OverflowError as e:
                # 特殊处理溢出错误（通常是时间索引问题）
                logger.error(f"  ✗ 超参尝试失败 (trial {current}): 数值溢出 - {e}")
                logger.debug(f"  溢出参数: {params}")
                return {"loss": float('inf'), "status": STATUS_OK}
            
            except Exception as e:
                logger.error(f"  ✗ 超参尝试失败 (trial {current}): {type(e).__name__}: {e}")
                return {"loss": float('inf'), "status": STATUS_OK}

        # 运行优化（使用 Hyperopt 内置早停机制）
        fmin(
            fn=objective,
            space=space,
            algo=tpe.suggest,
            max_evals=max_evals,
            trials=trials,
            early_stop_fn=no_progress_loss(patience) if early_stop_enabled else None,
            rstate=np.random.default_rng(None),
            verbose=False
        )

        if best_params is None:
            logger.warning("未找到有效的超参数组合")
            return {}

        # 将 choice 索引/值解析为实际值（如果需要）
        try:
            resolved = space_eval(space, best_params)
        except Exception:
            # 如果解析失败，直接返回 best_params
            resolved = best_params
        
        # 记录优化摘要（参考 GB 实现）
        actual_evals = len(trials.trials)
        is_early_stopped = actual_evals < max_evals
        
        if mlflow.active_run():
            mlflow.log_metric("hyperopt_summary/total_evals", max_evals)
            mlflow.log_metric("hyperopt_summary/actual_evals", actual_evals)
            mlflow.log_metric("hyperopt_summary/best_loss", best_score[0])
            
            if early_stop_enabled:
                mlflow.log_metric("hyperopt_summary/early_stop_enabled", 1.0)
                mlflow.log_metric("hyperopt_summary/early_stopped", 1.0 if is_early_stopped else 0.0)
                mlflow.log_metric("hyperopt_summary/patience_used", patience)
                
                if is_early_stopped:
                    time_saved_pct = ((max_evals - actual_evals) / max_evals * 100) if max_evals > 0 else 0
                    mlflow.log_metric("hyperopt_summary/time_saved_pct", time_saved_pct)
                    logger.info(
                        f"早停统计: 在 {actual_evals}/{max_evals} 次停止, "
                        f"节省 {time_saved_pct:.1f}% 时间"
                    )

        logger.info(f"Prophet 超参数优化完成，最佳参数: {resolved}, 最佳 {metric}: {best_score[0]:.4f}")
        return resolved

    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        使用 ProphetWrapper 包装模型，支持标准的 MLflow 推理接口。
        
        Args:
            artifact_path: MLflow artifact 路径
            
        Raises:
            RuntimeError: 模型未训练
            Exception: 模型序列化失败
        """
        from .prophet_wrapper import ProphetWrapper
        
        self._check_fitted()
        
        logger.info("开始保存 Prophet 模型到 MLflow")
        logger.info(f"artifact_path: {artifact_path}")
        logger.info(f"artifact_path: {artifact_path}")
        logger.info(f"training_frequency: {self.frequency}")
        
        # 记录模型元数据
        if mlflow.active_run():
            import sktime
            try:
                import prophet
                prophet_version = prophet.__version__
            except:
                prophet_version = "unknown"
            
            metadata = {
                'model_type': 'Prophet',
                'training_frequency': self.frequency,
                'data_length': len(self.last_train_data) if hasattr(self, 'last_train_data') and self.last_train_data is not None else 0,
                'sktime_version': sktime.__version__,
                'prophet_version': prophet_version,
                'prophet_params': self.prophet_params,
            }
            
            try:
                mlflow.log_dict(metadata, "model_metadata.json")
                logger.info("✓ 元数据已记录")
            except Exception as e:
                logger.warning(f"元数据记录失败: {e}")
        
        # 检查模型是否已训练
        if not self.is_fitted or self.model is None:
            raise RuntimeError("模型未训练，无法保存")
        
        # 创建 Wrapper
        logger.info("创建 ProphetWrapper...")
        wrapped_model = ProphetWrapper(
            model=self.model,
            training_frequency=self.frequency,
            prophet_params=self.prophet_params
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
            logger.info(f"✓ 模型已保存到 MLflow: {artifact_path}")
        except Exception as e:
            logger.error(f"✗ 模型保存失败: {type(e).__name__}: {e}")
            logger.error("可能原因:")
            logger.error("  1. sktime Prophet 模型包含不可序列化的对象")
            logger.error("  2. prophet 库版本不兼容")
            logger.error("  3. 内存不足或磁盘空间不足")
            logger.error(f"调试信息: backend={self._backend}, frequency={self.frequency}")
            import traceback
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            logger.error("=" * 60)
            raise
            logger.error("=" * 60)
            raise
