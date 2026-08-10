# -*- coding: utf-8 -*-
"""_parse_billing_period 解析规则单元测试。

覆盖范围:
- 纯 date / naive ISO datetime / Z 后缀 / 带偏移量 / 反向 swap / 跨日 / 失败路径
- 与 transaction_log.billing_date 的存储层语义对齐(UTC 日历日)

TDD 用例：本文件直接锁定账期解析的外部行为。
"""
from datetime import date

import pytest

from apps.cmdb.nats.nats import _parse_billing_period


def test_pure_date_passes():
    """['YYYY-MM-DD', 'YYYY-MM-DD'] → 端点直接当作 date 返回。"""
    assert _parse_billing_period(["2024-07-01", "2024-07-31"]) == (
        date(2024, 7, 1),
        date(2024, 7, 31),
    )


def test_local_datetime_treated_as_utc():
    """naive ISO datetime(无时区) → 视为 UTC,只取日历日。"""
    assert _parse_billing_period(
        ["2024-07-01T00:00:00", "2024-07-31T23:59:59"]
    ) == (date(2024, 7, 1), date(2024, 7, 31))


def test_utc_z_millisecond():
    """带 Z 后缀毫秒级 ISO datetime → 归 UTC 取 date。"""
    # 这条正是生产环境里 KPI 卡发出的载荷原貌。
    assert _parse_billing_period(
        ["2024-06-30T16:00:00.000Z", "2024-07-02T16:00:00.000Z"]
    ) == (date(2024, 6, 30), date(2024, 7, 2))


def test_offset_plus_0800():
    """带 +08:00 偏移 → 转 UTC 后取 date。
    2024-07-01T08:00:00+08:00 == 2024-07-01T00:00:00Z → date(7,1)。"""
    assert _parse_billing_period(
        ["2024-07-01T08:00:00+08:00", "2024-07-31T08:00:00+08:00"]
    ) == (date(2024, 7, 1), date(2024, 7, 31))


def test_swap_when_inverted():
    """start > end 时自动 swap,允许前端 RangePicker 反向选区。"""
    assert _parse_billing_period(["2024-07-31", "2024-07-01"]) == (
        date(2024, 7, 1),
        date(2024, 7, 31),
    )


def test_negative_offset_cross_midnight_utc():
    """-08:00 偏移跨越 UTC 午夜:2024-06-30T20:00:00-08:00 == 2024-07-01T04:00:00Z。
    验证时区归一会把"看似 6/30"的本地时间映射到"7/1"的 UTC 日。"""
    assert _parse_billing_period(
        ["2024-06-30T20:00:00-08:00", "2024-07-02T20:00:00-08:00"]
    ) == (date(2024, 7, 1), date(2024, 7, 3))


def test_empty_list_returns_none():
    assert _parse_billing_period([]) is None


def test_wrong_length_returns_none():
    assert _parse_billing_period(["2024-07-01"]) is None
    assert _parse_billing_period(["2024-07-01", "2024-07-31", "2024-08-01"]) is None
    assert _parse_billing_period(None) is None


def test_non_string_element_returns_none():
    """数字、None、对象等非字符串元素 → None。"""
    assert _parse_billing_period([123, "2024-07-01"]) is None
    assert _parse_billing_period([None, "2024-07-01"]) is None
    assert _parse_billing_period([{"d": "2024-07-01"}, "2024-07-01"]) is None


def test_unparseable_string_returns_none():
    """完全无法解析的字符串 → None,不留半成品。"""
    assert _parse_billing_period(["not-a-date", "2024-07-01"]) is None


def test_numeric_timestamp_returns_none():
    """秒级/毫秒级数字时间戳本期**显式不支持**,避免歧义。"""
    assert _parse_billing_period([1719792000, 1722470400]) is None
    # 毫秒级时间戳同样不接受
    assert _parse_billing_period([1719792000000, 1722470400000]) is None
