# -- coding: utf-8 --
# @File: time_util.py
# @Time: 2025/8/27 14:53
# @Author: windyzhao

from datetime import datetime


def format_time_iso(time_str: str):
    """
    将 "YYYY-MM-DD HH:MM:SS" 格式的时间字符串转换为 ISO 8601 格式，精确到毫秒，并附加 'Z' 表示 UTC 时间。
    例如，"2023-10-05 14:30:00" ->
    "2023-10-05T14:30:00.000Z"
    :param time_str: 输入的时间字符串，格式为 "YYYY-MM-DD HH:MM:SS"
    :return: 转换后的 ISO 8601 格式时间字符串
    """
    # 解析为datetime对象
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    # 转换为ISO 8601格式（UTC时区，带毫秒和Z后缀）
    iso_format = dt.isoformat(timespec='milliseconds') + 'Z'

    return iso_format


def format_timestamp(time_str: str):
    """
    将 "YYYY-MM-DD HH:MM:SS" 格式的时间字符串转换为时间戳（秒级别）。
    例如，"2023-10-05 14:30:00" -> 1696500600
    """
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    timestamp = dt.timestamp()
    formatted_timestamp = str(int(timestamp))
    return formatted_timestamp
