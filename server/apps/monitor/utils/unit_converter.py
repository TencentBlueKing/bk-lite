"""
指标单位自适应工具

提供指标数据的单位换算功能，自动选择合适的单位以便于用户浏览。
依赖: pint 库 (需要在 pyproject.toml 中添加: pint>=0.23)
"""

from typing import List, Optional, Tuple

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.unit_converter import UnitConverterConstants


class UnitConverter:
    """
    指标单位转换器

    使用 pint 库实现单位自动适配和转换功能
    支持常见的物理单位：字节、时间、百分比、速率等
    """

    _ureg = None  # 单位注册表（延迟初始化）

    @classmethod
    def _get_ureg(cls):
        """获取 pint 单位注册表（延迟初始化）"""
        if cls._ureg is None:
            try:
                import pint
                cls._ureg = pint.UnitRegistry()

                # 注册自定义单位
                for definition in UnitConverterConstants.PINT_CUSTOM_DEFINITIONS:
                    cls._ureg.define(definition)

            except ImportError as e:
                logger.error("pint 库未安装，请运行: uv add pint")
                raise ImportError("pint library is required for unit conversion. Install it with: uv add pint") from e

        return cls._ureg

    @classmethod
    def _normalize_unit(cls, unit: str) -> str:
        """
        标准化单位字符串

        :param unit: 原始单位字符串
        :return: 标准化后的单位
        """
        if not unit:
            return ''

        unit = unit.strip()
        unit_lower = unit.lower()

        # 如果在映射表中，返回标准化的单位（保持原有大小写）
        if unit_lower in UnitConverterConstants.UNIT_MAPPING:
            return UnitConverterConstants.UNIT_MAPPING[unit_lower]

        # 否则返回原始单位（去除首尾空格）
        return unit

    @classmethod
    def _detect_unit_category(cls, unit: str) -> Optional[str]:
        """
        检测单位所属的类别

        :param unit: 单位字符串
        :return: 单位类别，如 'byte', 'time', 'byte_rate' 等
        """
        normalized_unit = cls._normalize_unit(unit)

        # 检查是否在预定义的单位序列中
        for category, units in UnitConverterConstants.UNIT_PREFERENCES.items():
            if normalized_unit.upper() in [u.upper() for u in units]:
                return category

        # 特殊处理：检测二进制单位 (KiB, MiB, GiB 等)
        if any(binary_suffix in normalized_unit.upper() for binary_suffix in ['KIB', 'MIB', 'GIB', 'TIB', 'PIB']):
            if '/s' in normalized_unit.lower() or '/sec' in normalized_unit.lower():
                return 'binary_byte_rate'
            return 'binary_byte'

        # 特殊处理：检测二进制比特单位 (Kibit, Mibit, Gibit 等)
        if any(binary_suffix in normalized_unit.upper() for binary_suffix in ['KIBIT', 'MIBIT', 'GIBIT', 'TIBIT']):
            if '/s' in normalized_unit.lower() or '/sec' in normalized_unit.lower():
                return 'binary_bit_rate'
            return 'binary_bit'

        # 尝试使用 pint 检测维度
        try:
            ureg = cls._get_ureg()
            quantity = ureg.parse_expression(normalized_unit)

            # 根据维度判断类别
            dimensionality = str(quantity.dimensionality)

            if '[length] ** 3' in dimensionality or 'byte' in dimensionality.lower():
                return 'byte'
            elif '[time]' in dimensionality:
                return 'time'
            elif '1 / [time]' in dimensionality:
                return 'frequency'
            elif 'byte' in dimensionality.lower() and '/ [time]' in dimensionality:
                return 'byte_rate'

        except Exception as e:
            logger.warning(f"无法检测单位 '{unit}' 的类别: {e}")

        return None

    @classmethod
    def suggest_unit(cls, values: List[float], source_unit: str, strategy: str = None) -> str:
        """
        根据数值范围建议合适的单位

        :param values: 数值列表
        :param source_unit: 原始单位
        :param strategy: 选择策略，可选值:
                        - 'median': 中位数（默认，抗干扰）
                        - 'max': 最大值（确保所有值都能良好显示）
                        - 'mean': 平均值（平衡方案）
                        - 'p95': 95分位数（忽略极端值）
        :return: 建议的目标单位
        """
        if strategy is None:
            strategy = UnitConverterConstants.STRATEGY_MEDIAN

        if not values:
            logger.warning("数值列表为空，返回原始单位")
            return source_unit

        # 过滤掉 None 和无效值
        valid_values = [v for v in values if v is not None and not (isinstance(v, float) and (v != v))]  # 过滤 NaN

        if not valid_values:
            logger.warning("没有有效的数值，返回原始单位")
            return source_unit

        # 标准化单位
        normalized_unit = cls._normalize_unit(source_unit)

        # 检测单位类别
        category = cls._detect_unit_category(normalized_unit)

        if not category:
            logger.warning(f"未识别的单位类别: {source_unit}，返回原始单位")
            return source_unit

        # 获取该类别的单位序列
        unit_sequence = UnitConverterConstants.UNIT_PREFERENCES.get(category, [])

        if not unit_sequence:
            return source_unit

        # 根据策略计算参考值
        reference_value = cls._calculate_reference_value(valid_values, strategy)

        logger.debug(f"使用 {strategy} 策略，参考值: {reference_value}")

        # 百分比特殊处理：不转换
        if category == 'percent':
            return source_unit

        # 计数类型特殊处理
        if category == 'count':
            return cls._suggest_count_unit(reference_value, unit_sequence)

        # 使用 pint 进行单位适配
        try:
            ureg = cls._get_ureg()
            quantity = reference_value * ureg.parse_expression(normalized_unit)

            # 遍历单位序列，找到最合适的单位
            best_unit = normalized_unit
            best_magnitude = abs(reference_value)

            for target_unit in unit_sequence:
                try:
                    converted = quantity.to(target_unit)
                    magnitude = abs(converted.magnitude)

                    # 理想的数值范围：使用常量配置
                    if UnitConverterConstants.IDEAL_VALUE_RANGE_MIN <= magnitude < UnitConverterConstants.IDEAL_VALUE_RANGE_MAX:
                        return target_unit

                    # 记录最接近理想范围的单位
                    if abs(magnitude - UnitConverterConstants.IDEAL_VALUE_CENTER) < abs(best_magnitude - UnitConverterConstants.IDEAL_VALUE_CENTER):
                        best_unit = target_unit
                        best_magnitude = magnitude

                except Exception:
                    continue

            return best_unit

        except Exception as e:
            logger.warning(f"单位建议失败: {e}，返回原始单位")
            return source_unit

    @classmethod
    def _calculate_reference_value(cls, values: List[float], strategy: str) -> float:
        """
        根据策略计算参考值

        :param values: 数值列表
        :param strategy: 策略名称
        :return: 参考值
        """
        import statistics

        if strategy == UnitConverterConstants.STRATEGY_MAX:
            return max(values)
        elif strategy == UnitConverterConstants.STRATEGY_MEAN:
            return statistics.mean(values)
        elif strategy == UnitConverterConstants.STRATEGY_P95:
            # 95分位数
            sorted_values = sorted(values)
            index = int(len(sorted_values) * 0.95)
            return sorted_values[min(index, len(sorted_values) - 1)]
        else:  # 默认使用 median
            return statistics.median(values)

    @classmethod
    def _suggest_count_unit(cls, value: float, unit_sequence: List[str]) -> str:
        """
        为计数类型建议单位

        :param value: 参考数值
        :param unit_sequence: 单位序列
        :return: 建议单位
        """
        if not unit_sequence:
            return ''

        # 使用常量配置的阈值
        thresholds = UnitConverterConstants.COUNT_UNIT_THRESHOLDS

        # 遍历阈值，找到合适的单位
        for i, threshold in enumerate(thresholds):
            # 如果值小于下一个阈值，使用当前单位
            if i + 1 < len(unit_sequence) and value < threshold:
                return unit_sequence[i]

        # 如果值超过所有阈值，使用最大的单位
        return unit_sequence[min(len(thresholds), len(unit_sequence) - 1)]

    @classmethod
    def convert_values(cls, values: List[float], source_unit: str, target_unit: str) -> List[float]:
        """
        将数值列表从源单位转换到目标单位

        :param values: 数值列表
        :param source_unit: 源单位
        :param target_unit: 目标单位
        :return: 转换后的数值列表
        """
        if not values:
            return []

        # 标准化单位
        normalized_source = cls._normalize_unit(source_unit)
        normalized_target = cls._normalize_unit(target_unit)

        # 如果单位相同，直接返回
        if normalized_source.upper() == normalized_target.upper():
            return values

        # 检测单位类别
        category = cls._detect_unit_category(normalized_source)

        # 计数类型特殊处理
        if category == 'count':
            return cls._convert_count_values(values, normalized_source, normalized_target)

        # 使用 pint 进行转换
        try:
            ureg = cls._get_ureg()
            converted_values = []

            for value in values:
                if value is None or (isinstance(value, float) and value != value):  # None 或 NaN
                    converted_values.append(value)
                    continue

                quantity = value * ureg.parse_expression(normalized_source)
                converted = quantity.to(normalized_target)
                converted_values.append(converted.magnitude)

            return converted_values

        except Exception as e:
            logger.error(f"单位转换失败 ({source_unit} -> {target_unit}): {e}")
            return values

    @classmethod
    def _convert_count_values(cls, values: List[float], source_unit: str, target_unit: str) -> List[float]:
        """
        转换计数类型的数值

        :param values: 数值列表
        :param source_unit: 源单位
        :param target_unit: 目标单位
        :return: 转换后的数值列表
        """
        # 使用常量配置的倍数映射
        unit_multipliers = UnitConverterConstants.COUNT_UNIT_MULTIPLIERS

        source_multiplier = unit_multipliers.get(source_unit.upper(), 1)
        target_multiplier = unit_multipliers.get(target_unit.upper(), 1)

        if source_multiplier == target_multiplier:
            return values

        ratio = source_multiplier / target_multiplier

        return [v * ratio if v is not None else v for v in values]

    @classmethod
    def format_value(cls, value: float, unit: str, precision: int = None) -> str:
        """
        格式化数值和单位为可读字符串

        :param value: 数值
        :param unit: 单位
        :param precision: 小数精度
        :return: 格式化后的字符串，如 "1.23 MB"
        """
        if precision is None:
            precision = UnitConverterConstants.DEFAULT_PRECISION

        if value is None or (isinstance(value, float) and value != value):
            return "N/A"

        # 根据数值大小动态调整精度，使用常量配置
        if abs(value) >= 100:
            effective_precision = max(0, precision - 1)
        elif abs(value) >= 10:
            effective_precision = precision
        else:
            effective_precision = precision + 1

        # 格式化数值
        formatted_value = f"{value:.{effective_precision}f}"

        # 移除多余的零
        if '.' in formatted_value:
            formatted_value = formatted_value.rstrip('0').rstrip('.')

        return f"{formatted_value} {unit}".strip()

    @classmethod
    def auto_convert(cls, values: List[float], source_unit: str, precision: int = None, strategy: str = None) -> Tuple[List[float], str]:
        """
        自动转换：建议单位并转换数值

        :param values: 数值列表
        :param source_unit: 源单位
        :param precision: 小数精度（用于日志）
        :param strategy: 选择策略 ('median', 'max', 'mean', 'p95')
        :return: (转换后的数值列表, 目标单位)
        """
        if strategy is None:
            strategy = UnitConverterConstants.STRATEGY_MEDIAN

        try:
            # 建议目标单位
            target_unit = cls.suggest_unit(values, source_unit, strategy)

            # 转换数值
            converted_values = cls.convert_values(values, source_unit, target_unit)

            logger.debug(f"自动单位转换 ({strategy}): {source_unit} -> {target_unit}, 样例: {values[:3]} -> {converted_values[:3]}")

            return converted_values, target_unit

        except Exception as e:
            logger.error(f"自动单位转换失败: {e}")
            return values, source_unit
