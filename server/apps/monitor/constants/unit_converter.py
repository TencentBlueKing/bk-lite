"""
单位转换相关常量

定义单位转换器使用的所有常量配置
"""


class UnitConverterConstants:
    """单位转换器常量配置"""

    # 支持的单位类别及其首选单位序列（从小到大）
    UNIT_PREFERENCES = {
        # 字节单位（十进制，1000 进制）
        'byte': ['B', 'KB', 'MB', 'GB', 'TB', 'PB'],
        'bit': ['bit', 'Kbit', 'Mbit', 'Gbit', 'Tbit'],

        # 字节单位（二进制，1024 进制）- IEC 标准
        'binary_byte': ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'],
        'binary_bit': ['bit', 'Kibit', 'Mibit', 'Gibit', 'Tibit'],

        # 时间单位
        'time': ['ns', 'us', 'ms', 's', 'min', 'h', 'd'],

        # 频率单位
        'frequency': ['Hz', 'KHz', 'MHz', 'GHz'],

        # 百分比（无需转换）
        'percent': ['%'],

        # 速率单位（十进制）
        'byte_rate': ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s'],
        'bit_rate': ['bit/s', 'Kbit/s', 'Mbit/s', 'Gbit/s', 'Tbit/s'],
        'ops_rate': ['ops/s', 'Kops/s', 'Mops/s', 'Gops/s'],

        # 速率单位（二进制）
        'binary_byte_rate': ['B/s', 'KiB/s', 'MiB/s', 'GiB/s', 'TiB/s'],
        'binary_bit_rate': ['bit/s', 'Kibit/s', 'Mibit/s', 'Gibit/s', 'Tibit/s'],

        # 计数单位
        'count': ['', 'K', 'M', 'B', 'T'],
    }

    # 单位映射：将常见的单位字符串映射到标准格式
    UNIT_MAPPING = {
        # 字节（十进制）
        'bytes': 'B',
        'byte': 'B',
        'kb': 'KB',
        'mb': 'MB',
        'gb': 'GB',
        'tb': 'TB',
        'pb': 'PB',

        # 字节（二进制 - IEC 标准）
        'kib': 'KiB',
        'mib': 'MiB',
        'gib': 'GiB',
        'tib': 'TiB',
        'pib': 'PiB',
        'kibibyte': 'KiB',
        'mebibyte': 'MiB',
        'gibibyte': 'GiB',
        'tebibyte': 'TiB',
        'pebibyte': 'PiB',

        # 比特（二进制）
        'kibit': 'Kibit',
        'mibit': 'Mibit',
        'gibit': 'Gibit',
        'tibit': 'Tibit',
        'kibibit': 'Kibit',
        'mebibit': 'Mibit',
        'gibibit': 'Gibit',
        'tebibit': 'Tibit',

        # 时间
        'nanosecond': 'ns',
        'microsecond': 'us',
        'millisecond': 'ms',
        'second': 's',
        'minute': 'min',
        'hour': 'h',
        'day': 'd',

        # 速率（十进制）
        'bytes/s': 'B/s',
        'bytes/sec': 'B/s',
        'kb/s': 'KB/s',
        'mb/s': 'MB/s',
        'gb/s': 'GB/s',

        # 速率（二进制）
        'kib/s': 'KiB/s',
        'mib/s': 'MiB/s',
        'gib/s': 'GiB/s',
        'tib/s': 'TiB/s',

        # 百分比
        'percentage': '%',
        'percent': '%',

        # 频率
        'hertz': 'Hz',
        'khz': 'KHz',
        'mhz': 'MHz',
        'ghz': 'GHz',
    }

    # 计数单位的倍数映射
    COUNT_UNIT_MULTIPLIERS = {
        '': 1,
        'K': 1000,
        'M': 1000000,
        'B': 1000000000,
        'T': 1000000000000,
    }

    # 计数单位建议的阈值（对应 '', 'K', 'M', 'B', 'T'）
    COUNT_UNIT_THRESHOLDS = [1000, 1000000, 1000000000, 1000000000000]

    # pint 自定义单位定义
    PINT_CUSTOM_DEFINITIONS = [
        'percent = 0.01 = %',
        'ops = count',
        'Kops = 1000 * ops',
        'Mops = 1000000 * ops',
        'Gops = 1000000000 * ops',
    ]

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

