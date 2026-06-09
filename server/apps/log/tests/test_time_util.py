"""log.utils.time_util.TimeHelper 纯单元测试。

规格：get_time_range("5m"/"1h"/...) 返回 (start, end) 两个 ISO 毫秒+Z 字符串，
end 为当前 UTC，start = end - 区间；非法格式/单位抛 ValueError。
"""

from datetime import datetime

import pytest

from apps.log.utils.time_util import TimeHelper

pytestmark = pytest.mark.unit


def _parse(s):
    # "2024-01-01T00:00:00.000Z" -> datetime
    assert s.endswith("Z")
    return datetime.strptime(s[:-1], "%Y-%m-%dT%H:%M:%S.%f")


@pytest.mark.parametrize("range_str,seconds", [
    ("30s", 30),
    ("5m", 5 * 60),
    ("2h", 2 * 3600),
    ("1d", 86400),
])
def test_区间长度正确(range_str, seconds):
    start, end = TimeHelper.get_time_range(range_str)
    delta = _parse(end) - _parse(start)
    assert abs(delta.total_seconds() - seconds) < 1  # 容忍亚秒级误差


def test_格式带毫秒与_z():
    start, end = TimeHelper.get_time_range("5m")
    for s in (start, end):
        assert s.endswith("Z")
        # 毫秒三位
        assert len(s.split(".")[1]) == 4  # "mmmZ"


def test_默认区间为_5m():
    start, end = TimeHelper.get_time_range()
    assert abs((_parse(end) - _parse(start)).total_seconds() - 300) < 1


def test_非法格式抛_valueerror():
    with pytest.raises(ValueError):
        TimeHelper.get_time_range("abc")


def test_不支持的单位抛_valueerror():
    with pytest.raises(ValueError):
        TimeHelper.get_time_range("5y")
