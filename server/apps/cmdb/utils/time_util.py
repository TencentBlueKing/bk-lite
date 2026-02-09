# -- coding: utf-8 --
# @File: time_util.py
# @Time: 2025/12/10 14:00
# @Author: roger060353
from datetime import datetime, date, time, timedelta
from typing import Any
from django.utils import timezone

try:
    # 只有安装了 python-dateutil 才能用，若项目已依赖可以解开注释做更智能的解析
    from dateutil import parser as date_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


def excel_serial_to_datetime(serial: float) -> datetime:
    """
    将 Excel 日期序列号转换为 UTC 时间。
    Excel 的起始日期是 1899-12-30（Windows），这里按常见情况处理。
    如项目内已经有类似函数，请复用项目已有实现。
    """
    # Excel 的 0 对应 1899-12-30
    base_date = datetime(1899, 12, 30, tzinfo=timezone.utc)
    return base_date + timedelta(days=serial)


def parse_cmdb_time(value: Any) -> str:
    """
    将各种可能的时间输入统一转换为 ISO8601 带时区字符串:
    例如: 2025-11-27T10:31:44.338913+00:00
    """
    dt: datetime | None = None
    # 1\) 已经是 datetime
    if isinstance(value, datetime):
        dt = value

    # 2\) 是 date 或 time，补全成 datetime
    elif isinstance(value, date) and not isinstance(value, datetime):
        # 当作当天 00:00:00
        dt = datetime(value.year, value.month, value.day)

    elif isinstance(value, time):
        # 使用今天的日期，或按业务要求处理
        today = datetime.utcnow().date()
        dt = datetime(today.year, today.month, today.day,
                      value.hour, value.minute, value.second, value.microsecond)

    # 3\) 数字类型，认为是 Excel 序列日期
    elif isinstance(value, (int, float)):
        dt = excel_serial_to_datetime(float(value))

    # 4\) 字符串类型
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("空时间字符串")

        # 4\.1 先尝试标准 ISO 格式
        try:
            # 支持 "2025-11-27T10:31:44.338913+00:00" 或 "2025-11-27 10:31:44"
            dt = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError:
            dt = None

        # 4\.2 常见格式尝试
        if dt is None:
            common_formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M",
                "%Y%m%d%H%M%S",
                "%Y%m%d",
            ]
            for fmt in common_formats:
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

        # 4\.3 若安装了 dateutil，做更智能的解析
        if dt is None and HAS_DATEUTIL:
            try:
                dt = date_parser.parse(text)
            except (ValueError, TypeError):
                dt = None

        if dt is None:
            # 统一走外层的 "格式错误" 分支
            raise ValueError(f"无法解析时间: {text}")

    else:
        raise ValueError(f"不支持的时间类型: {type(value)}")
    # 按要求输出格式: 2025-11-27T10:31:44.338913+00:00
    return dt.isoformat()
