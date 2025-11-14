# -- coding: utf-8 --
# @File: collect_util.py
# @Time: 2025/11/12 11:28
# @Author: windyzhao
from datetime import datetime, timedelta


def timestamp_gt_one_day_ago(collect_timestamp):
    """
    判断时间戳是否大于一天前
    """
    # 获取当前时间
    current_time = datetime.now()
    # 计算一天前的时间
    one_day_ago = current_time - timedelta(days=1)
    # 转换为时间戳
    one_day_ago_timestamp = int(one_day_ago.timestamp())
    return collect_timestamp < one_day_ago_timestamp
