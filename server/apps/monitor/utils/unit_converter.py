"""
指标单位自适应工具

提供指标数据的单位换算功能，自动选择合适的单位以便于用户浏览。
基于产品定义的单位体系，只有同一体系的单位才能互相转换。
不再依赖 pint 库，使用内置的体系定义进行转换。
"""

import statistics
from typing import List, Optional, Tuple

from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.unit_converter import UnitConverterConstants


class UnitConverter:
    """
    指标单位转换器

    基于产品定义的单位体系实现单位自动适配和转换功能
    支持：百分比、计数、数据（比特/字节）、数据速率、时间、频率等
    """

    @classmethod
    def _normalize_unit(cls, unit: str) -> str:
        """
        标准化单位字符串

        :param unit: 原始单位字符串
        :return: 标准化后的单位ID
        """
        if not unit:
            return "none"

        unit = unit.strip()
        unit_lower = unit.lower()

        # 直接查找单位ID映射
        if unit_lower in UnitConverterConstants.UNIT_ID_TO_NAME:
            return UnitConverterConstants.UNIT_ID_TO_NAME[unit_lower]

        # 返回原始单位（可能是未知单位）
        logger.warning(f"未识别的单位: {unit}")
        return unit_lower

    @classmethod
    def _detect_unit_system(cls, unit: str) -> Optional[str]:
        """
        检测单位所属的体系

        :param unit: 单位ID
        :return: 单位体系名称，如 'percent', 'count', 'data_bytes' 等
        """
        normalized_unit = cls._normalize_unit(unit)

        # 检查是否是独立单位（不支持转换）
        if normalized_unit in UnitConverterConstants.STANDALONE_UNITS:
            return None

        # 遍历所有体系，查找包含该单位的体系
        for system_name, system_config in UnitConverterConstants.UNIT_SYSTEMS.items():
            if normalized_unit in system_config["units"]:
                return system_name

        logger.warning(f"未找到单位 '{unit}' 所属的体系")
        return None

    @classmethod
    def _calculate_unit_multiplier(cls, unit: str, system_name: str) -> float:
        """
        计算单位相对于基准单位的倍数

        :param unit: 单位ID
        :param system_name: 单位体系名称
        :return: 倍数值
        """
        system_config = UnitConverterConstants.UNIT_SYSTEMS.get(system_name)
        if not system_config:
            return 1.0

        units = system_config["units"]
        if unit not in units:
            return 1.0

        unit_index = units.index(unit)

        # 特殊处理：时间体系（非固定进制）
        if system_name == "time":
            multipliers = system_config.get("multipliers", [])
            total_multiplier = 1.0
            for i in range(1, unit_index + 1):
                total_multiplier *= multipliers[i]
            return total_multiplier

        # 特殊处理：百分比体系
        if system_name == "percent":
            # percentunit (0.0-1.0) 是基准单位，倍数为 1
            # percent (0-100) 倍数为 0.01
            # 转换：percentunit值 * (1 / 0.01) = percent值
            # 即：0.5 * 100 = 50
            if unit == "percentunit":
                return 1.0  # percentunit 是基准
            elif unit == "percent":
                return 0.01  # percent 相对于 percentunit 的倍数
            return 1.0

        # 常规体系：固定进制
        base = system_config.get("base", 1000)
        return base**unit_index

    @classmethod
    def suggest_unit(
        cls, values: List[float], source_unit: str, strategy: str = None
    ) -> str:
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
            strategy = UnitConverterConstants.STRATEGY_P95

        if not values:
            logger.warning("数值列表为空，返回原始单位")
            return source_unit

        # 过滤掉 None 和无效值
        valid_values = [
            v
            for v in values
            if v is not None and not (isinstance(v, float) and (v != v))
        ]  # 过滤 NaN

        if not valid_values:
            logger.warning("没有有效的数值，返回原始单位")
            return source_unit

        # 标准化单位
        normalized_unit = cls._normalize_unit(source_unit)

        # 检测单位体系
        system_name = cls._detect_unit_system(normalized_unit)

        if not system_name:
            logger.debug(f"单位 '{source_unit}' 不支持转换或是独立单位")
            return source_unit

        # 获取体系配置
        system_config = UnitConverterConstants.UNIT_SYSTEMS.get(system_name)
        if not system_config:
            return source_unit

        unit_sequence = system_config["units"]

        # 根据策略计算参考值
        reference_value = cls._calculate_reference_value(valid_values, strategy)

        logger.debug(
            f"使用 {strategy} 策略，参考值: {reference_value}, 体系: {system_name}"
        )

        # 转换参考值到基准单位
        source_multiplier = cls._calculate_unit_multiplier(normalized_unit, system_name)
        base_value = reference_value * source_multiplier

        # 遍历单位序列，找到最合适的单位
        best_unit = normalized_unit
        best_magnitude = abs(reference_value)

        for target_unit in unit_sequence:
            target_multiplier = cls._calculate_unit_multiplier(target_unit, system_name)
            magnitude = abs(base_value / target_multiplier)

            # 理想的数值范围
            if (
                UnitConverterConstants.IDEAL_VALUE_RANGE_MIN
                <= magnitude
                < UnitConverterConstants.IDEAL_VALUE_RANGE_MAX
            ):
                return target_unit

            # 记录最接近理想范围的单位
            if abs(magnitude - UnitConverterConstants.IDEAL_VALUE_CENTER) < abs(
                best_magnitude - UnitConverterConstants.IDEAL_VALUE_CENTER
            ):
                best_unit = target_unit
                best_magnitude = magnitude

        return best_unit

    @classmethod
    def _calculate_reference_value(cls, values: List[float], strategy: str) -> float:
        """
        根据策略计算参考值

        :param values: 数值列表
        :param strategy: 策略名称
        :return: 参考值
        """
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
    def convert_values(
        cls, values: List[float], source_unit: str, target_unit: str
    ) -> List[float]:
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
        if normalized_source == normalized_target:
            return values

        # 检测源单位和目标单位的体系
        source_system = cls._detect_unit_system(normalized_source)
        target_system = cls._detect_unit_system(normalized_target)

        # 必须属于同一体系才能转换
        if source_system != target_system:
            logger.error(
                f"单位转换失败：'{source_unit}' 和 '{target_unit}' 不属于同一体系"
            )
            return values

        if not source_system:
            logger.error(f"单位 '{source_unit}' 不支持转换")
            return values

        # 计算转换比率
        source_multiplier = cls._calculate_unit_multiplier(
            normalized_source, source_system
        )
        target_multiplier = cls._calculate_unit_multiplier(
            normalized_target, target_system
        )

        if target_multiplier == 0:
            logger.error(f"目标单位倍数为 0，无法转换")
            return values

        conversion_ratio = source_multiplier / target_multiplier

        # 转换所有值
        converted_values = []
        for value in values:
            if value is None or (
                isinstance(value, float) and value != value
            ):  # None 或 NaN
                converted_values.append(value)
            else:
                converted_values.append(value * conversion_ratio)

        return converted_values

    @classmethod
    def format_value(cls, value: float, unit: str, precision: int = None) -> str:
        """
        格式化数值和单位为可读字符串

        :param value: 数值
        :param unit: 单位ID
        :param precision: 小数精度
        :return: 格式化后的字符串，如 "1.23 MB"
        """
        if precision is None:
            precision = UnitConverterConstants.DEFAULT_PRECISION

        if value is None or (isinstance(value, float) and value != value):
            return "N/A"

        # 根据数值大小动态调整精度
        if abs(value) >= 100:
            effective_precision = max(0, precision - 1)
        elif abs(value) >= 10:
            effective_precision = precision
        else:
            effective_precision = precision + 1

        # 格式化数值
        formatted_value = f"{value:.{effective_precision}f}"

        # 移除多余的零
        if "." in formatted_value:
            formatted_value = formatted_value.rstrip("0").rstrip(".")

        # 获取展示单位
        normalized_unit = cls._normalize_unit(unit)
        display_unit = UnitConverterConstants.DISPLAY_UNIT_MAPPING.get(
            normalized_unit, normalized_unit
        )

        if display_unit:
            return f"{formatted_value} {display_unit}".strip()
        else:
            return formatted_value

    @classmethod
    def auto_convert(
        cls,
        values: List[float],
        source_unit: str,
        precision: int = None,
        strategy: str = None,
    ) -> Tuple[List[float], str]:
        """
        自动转换：建议单位并转换数值

        :param values: 数值列表
        :param source_unit: 源单位
        :param precision: 小数精度（用于日志）
        :param strategy: 选择策略 ('median', 'max', 'mean', 'p95')
        :return: (转换后的数值列表, 目标单位ID)
        """
        if strategy is None:
            strategy = UnitConverterConstants.STRATEGY_P95

        try:
            # 建议目标单位
            target_unit = cls.suggest_unit(values, source_unit, strategy)

            # 转换数值
            converted_values = cls.convert_values(values, source_unit, target_unit)

            # 获取展示单位（用于日志）
            display_source = UnitConverterConstants.DISPLAY_UNIT_MAPPING.get(
                cls._normalize_unit(source_unit), source_unit
            )
            display_target = UnitConverterConstants.DISPLAY_UNIT_MAPPING.get(
                cls._normalize_unit(target_unit), target_unit
            )

            logger.debug(
                f"自动单位转换 ({strategy}): {display_source} -> {display_target}, 样例: {values[:3]} -> {converted_values[:3]}"
            )

            return converted_values, target_unit

        except Exception as e:
            logger.error(f"自动单位转换失败: {e}")
            return values, source_unit

    @classmethod
    def get_display_unit(cls, unit: str) -> str:
        """
        获取单位的展示格式

        :param unit: 单位ID
        :return: 展示格式，如 'KB', '%', 'ms' 等
        """
        normalized_unit = cls._normalize_unit(unit)
        return UnitConverterConstants.DISPLAY_UNIT_MAPPING.get(
            normalized_unit, normalized_unit
        )

    @classmethod
    def is_convertible(cls, source_unit: str, target_unit: str) -> bool:
        """
        判断两个单位是否可以互相转换

        :param source_unit: 源单位
        :param target_unit: 目标单位
        :return: 是否可以转换
        """
        normalized_source = cls._normalize_unit(source_unit)
        normalized_target = cls._normalize_unit(target_unit)

        if normalized_source == normalized_target:
            return True

        source_system = cls._detect_unit_system(normalized_source)
        target_system = cls._detect_unit_system(normalized_target)

        return source_system is not None and source_system == target_system

    @classmethod
    def get_all_units(cls) -> list:
        """
        获取所有支持的单位列表

        :return: 单位列表，每个单位包含：unit_id, unit_name, category, system, display_unit, description
        """
        units = []

        # 遍历所有体系
        for system_name, system_config in UnitConverterConstants.UNIT_SYSTEMS.items():
            unit_ids = system_config["units"]
            display_units = system_config.get("display_units", [])
            base = system_config.get("base")

            for i, unit_id in enumerate(unit_ids):
                display_unit = display_units[i] if i < len(display_units) else unit_id

                # 生成单位描述
                description = cls._generate_unit_description(unit_id, system_name, base)

                # 获取单位分类
                category = UnitConverterConstants.UNIT_CATEGORY_MAPPING.get(
                    unit_id, "Other"
                )

                units.append(
                    {
                        "unit_id": unit_id,
                        "unit_name": cls._get_unit_display_name(unit_id),
                        "category": category,
                        "system": system_name,
                        "display_unit": display_unit,
                        "description": description,
                        "is_standalone": False,
                    }
                )

        # 添加独立单位（不支持转换）
        for unit_id in UnitConverterConstants.STANDALONE_UNITS:
            display_unit = UnitConverterConstants.DISPLAY_UNIT_MAPPING.get(
                unit_id, unit_id
            )

            # 获取单位分类
            category = UnitConverterConstants.UNIT_CATEGORY_MAPPING.get(
                unit_id, "Other"
            )

            units.append(
                {
                    "unit_id": unit_id,
                    "unit_name": cls._get_unit_display_name(unit_id),
                    "category": category,
                    "system": None,
                    "display_unit": display_unit,
                    "description": "独立单位，不支持转换",
                    "is_standalone": True,
                }
            )

        return units

    @classmethod
    def _get_unit_display_name(cls, unit_id: str) -> str:
        """
        获取单位的显示名称（用于前端展示）

        :param unit_id: 单位ID
        :return: 显示名称
        """
        # 单位ID到显示名称的映射
        unit_display_names = {
            # Base
            "none": "none",
            "percent": "percent",
            # Count
            "counts": "counts",
            "thousand": "thousand (K)",
            "million": "million (Mil)",
            "billion": "billion (Bil)",
            "trillion": "trillion (Tri)",
            "quadrillion": "quadrillion (Quadr)",
            "quintillion": "quintillion (Quint)",
            "sextillion": "sextillion (Sext)",
            "septillion": "septillion (Sept)",
            # Data (bits)
            "bits": "bits (b)",
            "kilobits": "kilobits (Kb)",
            "megabits": "megabits (Mb)",
            "gigabits": "gigabits (Gb)",
            "terabits": "terabits (Tb)",
            "petabits": "petabits (Pb)",
            # Data (bytes)
            "bytes": "bytes (B)",
            "kibibytes": "kibibytes (KiB)",
            "mebibytes": "mebibytes (MiB)",
            "gibibytes": "gibibytes (GiB)",
            "tebibytes": "tebibytes (TiB)",
            "pebibytes": "pebibytes (PiB)",
            # Data Rate (bits)
            "bitps": "bits/sec (b/s)",
            "kbitps": "kilobits/sec (Kb/s)",
            "mbitps": "megabits/sec (Mb/s)",
            "gbitps": "gigabits/sec (Gb/s)",
            "tbitps": "terabits/sec (Tb/s)",
            "pbitps": "petabits/sec (Pb/s)",
            # Data Rate (bytes)
            "byteps": "bytes/sec (B/s)",
            "kibyteps": "kibibytes/sec (KiB/s)",
            "mibyteps": "mebibytes/sec (MiB/s)",
            "gibyteps": "gibibytes/sec (GiB/s)",
            "tibyteps": "tebibytes/sec (TiB/s)",
            "pibyteps": "pebibytes/sec (PiB/s)",
            # Time
            "ns": "nanoseconds (ns)",
            "µs": "microseconds (µs)",
            "ms": "milliseconds (ms)",
            "s": "seconds (s)",
            "m": "minutes (m)",
            "h": "hours (h)",
            "d": "days (d)",
            # Rate
            "cps": "counts/sec (cps)",
            "hertz": "Hertz (Hz)",
            "kilohertz": "Kilohertz (KHz)",
            "megahertz": "Megahertz (MHz)",
            "msps": "milliseconds/sec(ms/s)",  # 注意：括号前无空格
            # Temperature
            "celsius": "Celsius (°C)",
            "fahrenheit": "Fahrenheit (°F)",
            "kelvin": "Kelvin (K)",
            # Other
            "watts": "Watts (W)",
            "volts": "Volts (V)",
        }

        return unit_display_names.get(unit_id, unit_id)

    @classmethod
    def _generate_unit_description(
        cls, unit_id: str, system_name: str, base: int
    ) -> str:
        """
        生成单位描述

        :param unit_id: 单位ID
        :param system_name: 体系名称
        :param base: 进制
        :return: 描述文本
        """
        system_desc_map = {
            "percent": "百分比体系",
            "count": "计数体系 (1000进制)",
            "data_bits": "数据-比特体系 (1000进制)",
            "data_bytes": "数据-字节体系 (1024进制)",
            "data_rate_bits": "数据速率-比特体系 (1000进制)",
            "datarate_bytes": "数据速率-字节体系 (1024进制)",
            "time": "时间体系",
            "hertz": "频率体系 (1000进制)",
        }

        return system_desc_map.get(system_name, f"{system_name} 体系")

    @classmethod
    def get_units_by_system(cls, system_name: str = None) -> list:
        """
        按体系获取单位列表

        :param system_name: 体系名称，如果为 None 则按体系分组返回所有单位
        :return: 单位列表或分组字典
        """
        if system_name:
            # 返回指定体系的单位
            all_units = cls.get_all_units()
            return [unit for unit in all_units if unit["system"] == system_name]
        else:
            # 按体系分组返回
            all_units = cls.get_all_units()
            grouped = {}
            for unit in all_units:
                system = unit["system"] or "standalone"
                if system not in grouped:
                    grouped[system] = []
                grouped[system].append(unit)
            return grouped
