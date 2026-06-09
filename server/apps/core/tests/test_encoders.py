"""core.encoders.PrettyJSONEncoder 纯单元测试。

规格：强制 indent=4、sort_keys=True —— 无论调用方是否传入这些参数，
输出都应为缩进且按键排序的 JSON。
"""

import json

import pytest

from apps.core.encoders import PrettyJSONEncoder

pytestmark = pytest.mark.unit


def test_强制缩进与排序():
    out = json.dumps({"b": 1, "a": 2}, cls=PrettyJSONEncoder)
    # 按键排序：a 在 b 前；缩进 4：包含换行与四空格
    assert out == '{\n    "a": 2,\n    "b": 1\n}'


def test_即使调用方未要求排序也排序():
    out = json.dumps({"z": 1, "a": 1}, cls=PrettyJSONEncoder, sort_keys=False)
    assert out.index('"a"') < out.index('"z"')
