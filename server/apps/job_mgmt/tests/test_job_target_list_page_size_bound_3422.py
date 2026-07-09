"""回归测试:job_target_list page_size 必须有上限,防止 -1/超大值触发全表扫描无上界。

关联 Issue #3422:`[tech-debt][job_mgmt] job_target_list page_size=-1
触发全表扫描无上界,可远程触发 OOM`

修复契约:
- page_size=-1 必须被收敛到 MAX_TARGET_PAGE_SIZE 上界(默认 5000),而不是全量加载。
- page_size>MAX_TARGET_PAGE_SIZE 也必须被收敛,而不是切超大窗口。
- 返回 items 数量受 MAX_TARGET_PAGE_SIZE 限制。
- 当数据总数超过 MAX_TARGET_PAGE_SIZE 时,响应中需带 truncated=True 标记。
"""

import pytest

from apps.job_mgmt import nats_api
from apps.job_mgmt.models import Target

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def max_page_size(monkeypatch):
    """让 MAX_TARGET_PAGE_SIZE 设为小值(便于测试),不影响生产值。

    修复前 nats_api 不存在该常量,fixture 必须能优雅处理:缺失时仅设值,
    而不在 setup 阶段 AttributeError,这样每条用例都能独立跑出 RED 信号。
    """
    if not hasattr(nats_api, "MAX_TARGET_PAGE_SIZE"):
        monkeypatch.setattr(nats_api, "MAX_TARGET_PAGE_SIZE", 3, raising=False)
    else:
        monkeypatch.setattr(nats_api, "MAX_TARGET_PAGE_SIZE", 3)
    return 3


class TestJobTargetListPageSizeBound:
    def test_page_size_neg_one_is_capped(self, max_page_size):
        """page_size=-1 必须被收敛到 MAX_TARGET_PAGE_SIZE 上界,不能全量加载。"""
        for i in range(max_page_size + 5):
            Target.objects.create(name=f"h-{i}", ip=f"10.0.0.{i}", os_type="linux", team=[1])

        out = nats_api.job_target_list({"page_size": -1})

        assert out["result"] is True
        # count 仍反映全表(便于调用方知道真实规模)
        assert out["data"]["count"] == max_page_size + 5
        # items 数量被截断到上界
        assert len(out["data"]["items"]) == max_page_size
        # 必须有 truncated 提示,告知调用方数据被截断
        assert out["data"].get("truncated") is True

    def test_page_size_exceeds_max_is_capped(self, max_page_size):
        """page_size 大于 MAX_TARGET_PAGE_SIZE 也必须被收敛。"""
        for i in range(max_page_size + 2):
            Target.objects.create(name=f"h-{i}", ip=f"10.0.0.{i}", os_type="linux", team=[1])

        out = nats_api.job_target_list({"page_size": max_page_size + 100})

        assert out["result"] is True
        assert len(out["data"]["items"]) == max_page_size
        assert out["data"].get("truncated") is True

    def test_normal_page_size_works_without_truncation(self, max_page_size):
        """正常 page_size 不应被截断,truncated 应为 False。"""
        for i in range(max_page_size):
            Target.objects.create(name=f"h-{i}", ip=f"10.0.0.{i}", os_type="linux", team=[1])

        out = nats_api.job_target_list({"page_size": 2})

        assert out["result"] is True
        assert out["data"]["count"] == max_page_size
        assert len(out["data"]["items"]) == 2
        assert out["data"].get("truncated") is False

    def test_default_page_size_is_bounded(self, max_page_size):
        """不传 page_size 时走默认值,也不会触发全表扫描。"""
        for i in range(max_page_size + 10):
            Target.objects.create(name=f"h-{i}", ip=f"10.0.0.{i}", os_type="linux", team=[1])

        out = nats_api.job_target_list({})

        assert out["result"] is True
        # 默认 page_size 是 20,但若 MAX 更小则以 MAX 为准;此处 MAX=3
        assert len(out["data"]["items"]) <= max_page_size