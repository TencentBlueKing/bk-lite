"""dameng / tongweb / jboss / jetty placeholder e2e 统一测试。

【v4 Phase 6 补 license 阻塞对象】2026-07-10 — 这 4 个对象 stargazer 端 install_commands 故意
exit 1(license / 装包源不可达),fixture 落盘是 placeholder:
  - dameng:raw_stdout={}(空 dict,license_status=missing)
  - tongweb/jboss/jetty:raw_stdout=[]

CMDB 端无 plugin 类,但 e2e 仍验证"fixture 落盘 + 公共契约命中"两层,
等 license 解锁后(用户提供 license + 走 amd64 CI),把 placeholder 替换成真实 raw_stdout
即可升级到完整 3 层验证(契约 + 流水线 + 字段对齐)。
"""
import json

import jsonschema
import pytest

from apps.cmdb.tests.e2e.conftest import E2E_ROOT


PLACEHOLDER_MODEL_IDS = [
    "dameng",      # license missing
    "tongweb",     # aliyun + 东方通官网 镜像都不可达
    "jboss",       # wildfly 4 种装包方式都失败
    "jetty",       # ubuntu 22.04 apt 仓库无 jetty9 包
    "ambari",      # 2026-07-10 刚跑通(原以为不可达):ambari 无官方 docker 镜像,需手动装 license + JDK
    "server_bmc",  # 2026-07-10 刚跑通:Redfish mock 真实数据,但 CMDB 端无 plugin 走 placeholder
    "ibmmq",       # 2026-07-10 落盘确认(license 阻塞):IBM MQ 9.x 试用 license
    "highgo",      # 2026-07-10 Phase 1 跑通(国产 PG 兼容,临时复用 postgres 镜像),无 plugin 走 placeholder
    "nacos",       # 2026-07-10 Phase 1 跑通(阿里配置中心 v3.0.2),无 plugin 走 placeholder
    "tdsql",       # 2026-07-10 Phase 1 跑通(腾讯分布式 DB,临时复用 mysql 镜像),无 plugin 走 placeholder
]


def _load(rel_path: str):
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("model_id", PLACEHOLDER_MODEL_IDS)
def test_placeholder_fixture_satisfies_common_contract(model_id):
    """Placeholder 对象 fixture 仍命中公共契约(契约层验证)。

    验证:
    1) fixture 落盘存在
    2) 命中 00_common_contract(支持空 list / 空 dict)
    3) 标注 placeholder 状态(license_status / placeholder_reason / blocked_reason)
    """
    fixture_path = E2E_ROOT / "fixtures" / model_id / "01_stargazer_raw.json"
    assert fixture_path.exists(), f"{model_id} fixture 未落盘"

    fixture = _load(f"fixtures/{model_id}/01_stargazer_raw.json")
    contract = _load("schemas/00_common_contract.schema.json")
    jsonschema.validate(fixture, contract)

    # 验证 placeholder 状态标记(防止后续误以为"已跑通")
    is_placeholder = (
        fixture.get("license_status") == "missing"
        or "placeholder_reason" in fixture
        or "_placeholder_reason" in fixture
        or "blocked_reason" in fixture
    )
    assert is_placeholder, (
        f"{model_id} fixture 应标注 placeholder/license 状态"
        f"(license_status=missing / placeholder_reason / blocked_reason 之一)"
    )


def test_dameng_blocked_reason_documented():
    """dameng fixture 必带 blocked_reason 文档(供 license 解锁时回溯)。"""
    fixture = _load("fixtures/dameng/01_stargazer_raw.json")
    assert fixture.get("blocked_reason"), "dameng fixture 应有 blocked_reason 字段"
    assert fixture.get("next_steps"), "dameng fixture 应有 next_steps 字段"
    assert fixture.get("references"), "dameng fixture 应有 references 字段"