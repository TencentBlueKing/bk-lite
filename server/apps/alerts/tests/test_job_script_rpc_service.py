"""复现并锁定 JobMgmt 脚本相关 RPC 包装器的调用约定 bug。

线上报错（local RPC 模式 AppClient.run -> method(*args, **kwargs)）：
    get_job_mgmt_module_data() missing 4 required positional arguments:
    'child_module', 'page', 'page_size', and 'group_id'
根因：list_scripts/get_script 用单个位置 dict 调 get_job_mgmt_module_data，
而该函数要 5 个独立参数；且 get_job_mgmt_module_data 只返回 {id,name}，
拿不到 content/params -> get_script 必须走新的 job_script_detail 接口。

这些测试用 is_local_client=True 走真实本地 RPC 路径（与线上同一条），不打桩。
"""
import pytest

from apps.job_mgmt.models.script import Script
from apps.rpc.job_mgmt import JobMgmt


@pytest.mark.django_db
def test_list_scripts_returns_team_scripts_via_local_rpc():
    Script.objects.create(name="重启nginx", script_type="shell", content="echo hi", params=[], timeout=60, team=[7])
    # 另一团队的脚本不应出现
    Script.objects.create(name="别人家的脚本", script_type="shell", content="echo no", params=[], timeout=60, team=[99])

    result = JobMgmt(is_local_client=True).list_scripts(group_id=7, team=[7])

    names = [it["name"] for it in result["items"]]
    assert "重启nginx" in names
    assert "别人家的脚本" not in names


@pytest.mark.django_db
def test_get_script_returns_full_detail_via_local_rpc():
    script = Script.objects.create(
        name="清理磁盘", script_type="shell", content="echo {{svc}}", params=[{"name": "svc", "default": ""}], timeout=120, team=[7],
    )

    detail = JobMgmt(is_local_client=True).get_script(script.id, team=[7])

    assert detail is not None
    assert detail["content"] == "echo {{svc}}"
    assert detail["script_type"] == "shell"
    assert detail["params"] == [{"name": "svc", "default": ""}]
    assert detail["timeout"] == 120


@pytest.mark.django_db
def test_get_script_missing_returns_none():
    assert JobMgmt(is_local_client=True).get_script(999999, team=[7]) is None
