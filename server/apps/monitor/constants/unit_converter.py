"""
单位转换相关常量

定义单位转换器使用的所有常量配置
基于产品定义的单位体系，只有同一体系的单位才能互相转换
"""


class UnitConverterConstants:
    """单位转换器常量配置"""

    # 单位体系定义（按照产品文档，只有同一体系的单位才能互相转换）
    # 每个体系包含单位序列（从小到大）和换算基数
    UNIT_SYSTEMS = {
        # 百分比体系
        'percent': {
            'units': ['percentunit', 'percent'],  # percentunit (0.0-1.0) -> percent (0-100)
            'base': 1,
            'display_units': ['%', '%'],
            # percentunit 是基准单位，percent = 0.01 * percentunit（在倍数意义上）
            # 即：percentunit的值 * 100 = percent的值
        },

        # 计数体系（1000进制）
        'count': {
            'units': ['counts', 'thousand', 'million', 'billion', 'trillion', 'quadrillion', 'quintillion', 'sextillion', 'septillion'],
            'base': 1000,
            'display_units': ['', 'K', 'Mil', 'Bil', 'Tri', 'Quadr', 'Quint', 'Sext', 'Sept'],
        },

        # 数据-比特体系（1000进制）
        'data_bits': {
            'units': ['bits', 'kilobits', 'megabits', 'gigabits', 'terabits', 'petabits'],
            'base': 1000,
            'display_units': ['b', 'Kb', 'Mb', 'Gb', 'Tb', 'Pb'],
        },

        # 数据-字节体系（1024进制）
        'data_bytes': {
            'units': ['bytes', 'kibibytes', 'mebibytes', 'gibibytes', 'tebibytes', 'pebibytes'],
            'base': 1024,
            'display_units': ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'],
        },

        # 数据速率-比特体系（1000进制）
        'data_rate_bits': {
            'units': ['bitps', 'kbitps', 'mbitps', 'gbitps', 'tbitps', 'pbitps'],
            'base': 1000,
            'display_units': ['b/s', 'Kb/s', 'Mb/s', 'Gb/s', 'Tb/s', 'Pb/s'],
        },

        # 数据速率-字节体系（1024进制）
        'datarate_bytes': {
            'units': ['byteps', 'kibyteps', 'mibyteps', 'gibyteps', 'tibyteps', 'pibyteps'],
            'base': 1024,
            'display_units': ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s', 'PiB/s'],
        },

        # 时间体系
        'time': {
            'units': ['ns', 'µs', 'ms', 's', 'm', 'h', 'd'],
            'base': None,  # 非固定进制（1000, 1000, 1000, 60, 60, 24）
            'multipliers': [1, 1000, 1000, 1000, 60, 60, 24],  # 每级相对于前一级的倍数
            'display_units': ['ns', 'µs', 'ms', 's', 'min', 'hour', 'day'],
        },

        # 频率-赫兹体系（1000进制）
        'hertz': {
            'units': ['hertz', 'kilohertz', 'megahertz'],
            'base': 1000,
            'display_units': ['Hz', 'KHz', 'MHz'],
        },
    }

    # 单位ID到单位名称的映射（用于标准化）
    UNIT_ID_TO_NAME = {
        # Base
        'none': 'none',
        'percent': 'percent',
        'percentunit': 'percentunit',

        # Count
        'counts': 'counts',
        'thousand': 'thousand',
        'million': 'million',
        'billion': 'billion',
        'trillion': 'trillion',
        'quadrillion': 'quadrillion',
        'quintillion': 'quintillion',
        'sextillion': 'sextillion',
        'septillion': 'septillion',

        # Data (bits)
        'bits': 'bits',
        'kilobits': 'kilobits',
        'megabits': 'megabits',
        'gigabits': 'gigabits',
        'terabits': 'terabits',
        'petabits': 'petabits',

        # Data (bytes)
        'bytes': 'bytes',
        'kibibytes': 'kibibytes',
        'mebibytes': 'mebibytes',
        'gibibytes': 'gibibytes',
        'tebibytes': 'tebibytes',
        'pebibytes': 'pebibytes',

        # Data Rate (bits)
        'bitps': 'bitps',
        'kbitps': 'kbitps',
        'mbitps': 'mbitps',
        'gbitps': 'gbitps',
        'tbitps': 'tbitps',
        'pbitps': 'pbitps',

        # Data Rate (bytes)
        'byteps': 'byteps',
        'kibyteps': 'kibyteps',
        'mibyteps': 'mibyteps',
        'gibyteps': 'gibyteps',
        'tibyteps': 'tibyteps',
        'pibyteps': 'pibyteps',

        # Time
        'ns': 'ns',
        'µs': 'µs',
        'us': 'µs',  # 别名
        'ms': 'ms',
        's': 's',
        'm': 'm',
        'h': 'h',
        'd': 'd',

        # Rate
        'cps': 'cps',
        'hertz': 'hertz',
        'kilohertz': 'kilohertz',
        'megahertz': 'megahertz',
        'msps': 'msps',

        # Temperature
        'celsius': 'celsius',
        'fahrenheit': 'fahrenheit',
        'kelvin': 'kelvin',

        # Other
        'watts': 'watts',
        'volts': 'volts',
    }

    # 单位别名映射（兼容旧单位格式）
    UNIT_ALIASES = {
        # 百分比
        '%': 'percent',
        'percentage': 'percent',

        # 字节
        'b': 'bytes',
        'byte': 'bytes',
        'kib': 'kibibytes',
        'mib': 'mebibytes',
        'gib': 'gibibytes',
        'tib': 'tebibytes',
        'pib': 'pebibytes',

        # 比特
        'bit': 'bits',
        'kb': 'kilobits',
        'mb': 'megabits',
        'gb': 'gigabits',
        'tb': 'terabits',
        'pb': 'petabits',

        # 时间
        'nanosecond': 'ns',
        'microsecond': 'µs',
        'millisecond': 'ms',
        'second': 's',
        'minute': 'm',
        'min': 'm',
        'hour': 'h',
        'day': 'd',

        # 速率
        'b/s': 'byteps',
        'bytes/s': 'byteps',
        'bytes/sec': 'byteps',
        'kib/s': 'kibyteps',
        'mib/s': 'mibyteps',
        'gib/s': 'gibyteps',
        'tib/s': 'tibyteps',
        'pib/s': 'pibyteps',
        'bit/s': 'bitps',
        'bits/s': 'bitps',
        'kb/s': 'kbitps',
        'mb/s': 'mbitps',
        'gb/s': 'gbitps',
        'tb/s': 'tbitps',
        'pb/s': 'pbitps',

        # 频率
        'hz': 'hertz',
        'khz': 'kilohertz',
        'mhz': 'megahertz',

        # 计数
        'k': 'thousand',
        'mil': 'million',
        'bil': 'billion',
        'tri': 'trillion',
    }

    # 展示单位映射（单位名称 -> 展示格式）
    DISPLAY_UNIT_MAPPING = {
        'percent': '%',
        'percentunit': '%',
        'counts': '',
        'thousand': 'K',
        'million': 'Mil',
        'billion': 'Bil',
        'trillion': 'Tri',
        'quadrillion': 'Quadr',
        'quintillion': 'Quint',
        'sextillion': 'Sext',
        'septillion': 'Sept',
        'bits': 'b',
        'kilobits': 'Kb',
        'megabits': 'Mb',
        'gigabits': 'Gb',
        'terabits': 'Tb',
        'petabits': 'Pb',
        'bytes': 'B',
        'kibibytes': 'KiB',
        'mebibytes': 'MiB',
        'gibibytes': 'GiB',
        'tebibytes': 'TiB',
        'pebibytes': 'PiB',
        'bitps': 'b/s',
        'kbitps': 'Kb/s',
        'mbitps': 'Mb/s',
        'gbitps': 'Gb/s',
        'tbitps': 'Tb/s',
        'pbitps': 'Pb/s',
        'byteps': 'B/s',
        'kibyteps': 'KiB/s',
        'mibyteps': 'MiB/s',
        'gibyteps': 'GiB/s',
        'tibyteps': 'TiB/s',
        'pibyteps': 'PiB/s',
        'ns': 'ns',
        'µs': 'µs',
        'ms': 'ms',
        's': 's',
        'm': 'min',
        'h': 'hour',
        'd': 'day',
        'cps': 'cps',
        'hertz': 'Hz',
        'kilohertz': 'KHz',
        'megahertz': 'MHz',
        'msps': 'ms/s',
        'celsius': '°C',
        'fahrenheit': '°F',
        'kelvin': 'K',
        'watts': 'W',
        'volts': 'V',
        'none': '',
    }

    # 不支持转换的单位（独立单位）
    STANDALONE_UNITS = ['none', 'cps', 'msps', 'celsius', 'fahrenheit', 'kelvin', 'watts', 'volts']

    # 单位建议策略配置
    STRATEGY_MEDIAN = 'median'  # 中位数（默认，抗干扰）
    STRATEGY_MAX = 'max'  # 最大值（确保所有值都能良好显示）
    STRATEGY_MEAN = 'mean'  # 平均值（平衡方案）
    STRATEGY_P95 = 'p95'  # 95分位数（忽略极端值）

    # 理想数值显示范围
    IDEAL_VALUE_RANGE_MIN = 1
    IDEAL_VALUE_RANGE_MAX = 1000
    IDEAL_VALUE_CENTER = 100  # 最接近此值的单位为最佳选择

    # 数值格式化精度配置
    DEFAULT_PRECISION = 2
    PRECISION_LARGE_VALUE = 1  # 值 >= 100 时的精度
    PRECISION_MEDIUM_VALUE = 2  # 值 >= 10 时的精度
    PRECISION_SMALL_VALUE = 3  # 值 < 10 时的精度

