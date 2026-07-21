"""跨对象公共契约测试 —— 自动覆盖 v3+ 全部真实落盘对象的 fixture。

v4 Phase 1.3 任务:用 `pytest.mark.parametrize` 显式列举 27 个 model_id,
验证每个 `fixtures/<model_id>/01_stargazer_raw.json` 满足公共契约
(`schemas/00_common_contract.schema.json`)。

不在覆盖范围(已在 v4 排除):
- elasticsearch → stargazer 端 catalog 用 model_id=`es`,但 fixture 命名可能用 `es.json`/`elasticsearch.json`
  → factory 工厂用 `es`(见 conftest._MODEL_RUNNER_MAP)
- dameng / dameng 等 → CMDB 端无 plugin 类(待 v4 Phase 2 补)
- 其他 K8s / VMware / 云采集 → v3 明确排除
"""
import json
from pathlib import Path

import jsonschema
import pytest

E2E_ROOT = Path(__file__).parent
SCHEMAS_ROOT = E2E_ROOT / "schemas"
FIXTURES_ROOT = E2E_ROOT / "fixtures"


def _load_common_contract():
    with open(SCHEMAS_ROOT / "00_common_contract.schema.json", "r", encoding="utf-8") as f:
        return json.load(f)


# v3+ 阶段有 stargazer 真实落盘的对象(main 7 + worktree 20 = 27)
# 与 conftest.py:_MODEL_RUNNER_MAP 保持一致
# 工厂覆盖 31 个对象(包括 K8s/VMware/云采集的 protocol runner 等),
# 但 fixture 实际落盘只 27 个,未落盘的会 skip
COVERED_MODEL_IDS = [
    # main 7(已有 e2e 模板的对象,作为回归基线)
    "influxdb",
    "mysql",
    "nginx",
    "redis",
    # P0(本 change 任务阶段 3 目标)
    "postgresql",
    "mongodb",
    "tomcat",
    "rabbitmq",
    "kafka",
    "zookeeper",
    "haproxy",
    "elasticsearch",  # alias:es
    "es",              # 实际 fixture 命名
    # P1(本 change 任务阶段 4 目标)
    "keepalived",
    "openresty",
    "apache",
    "activemq",
    "dameng",
    "tongweb",
    "minio",
    "consul",
    # P2(本 change 任务阶段 5 目标)
    "etcd",
    "memcached",
    "squid",
    "rocketmq",
    "redis_sentinel",
    "jboss",
    "jetty",
    # 其他工厂覆盖但本 change 排除(stargazer 端无真实落盘 fixture 或 v3 排除)
    "mssql",      # 代码 BLOCKED(arm64)
    "oracle",     # v3 排除
    "iis",        # windows 专属,无 docker 镜像
    "hbase",      # hadoop 全家桶,需集群
    "docker",     # 单 host 镜像,非采集对象
    # Task 3:P1 云采集新增 — aliyun_ecs / vmware_vc 模式:fixture 用 flat dict(无 raw_stdout envelope)
    # 公共契约测试只覆盖有 raw_stdout envelope 的对象(形态 A/B/C);云采集对象走 plugin-driven 路径
    # 通过 conftest._MODEL_RUNNER_MAP 注册,不进 COVERED_MODEL_IDS(本 test 只针对 raw_stdout envelope 对象)
    # 不在此列的:hwcloud_ecs/vpc, qcloud_*, fusioninsight_*, zstack, h3c_cas,
    #            dameng_enterprise, redis_sentinel_enterprise
]


@pytest.mark.parametrize("model_id", COVERED_MODEL_IDS)
def test_stargazer_raw_satisfies_common_contract(model_id):
    """每个真实落盘对象的 fixture 必须满足公共契约。

    三步:
      1. 读公共契约 schema
      2. 读对象 fixture(若不存在,skip)
      3. jsonschema.validate(不抛 ValidationError = pass)
    """
    fixture_path = FIXTURES_ROOT / model_id / "01_stargazer_raw.json"
    if not fixture_path.exists():
        pytest.skip(f"fixture 未落盘: {fixture_path} (本任务未到该对象)")
    contract = _load_common_contract()
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)
    try:
        jsonschema.validate(fixture, contract)
    except jsonschema.ValidationError as e:
        pytest.fail(
            f"公共契约违规: model_id={model_id}, "
            f"路径: {' → '.join(str(p) for p in e.absolute_path)}, "
            f"错误: {e.message}"
        )


def test_common_contract_cover_no_orphan_model_id():
    """反向校验:COVERED_MODEL_IDS 列表里的每个 model_id 都能在 factory 找到。

    本 test 只针对 raw_stdout envelope 形态对象(形态 A/B/C);云采集 plugin-driven 对象
    (hwcloud_ecs / qcloud_*)不进 COVERED_MODEL_IDS,所以不参与双向一致性校验。
    只检查 test_covered ⊆ factory_covered(防止测试列了但 factory 未注册)。
    """
    from apps.cmdb.tests.e2e.conftest import _MODEL_RUNNER_MAP
    factory_covered = set(_MODEL_RUNNER_MAP.keys())
    test_covered = set(COVERED_MODEL_IDS)
    extra_in_test = test_covered - factory_covered
    assert not extra_in_test, (
        f"测试列了但工厂未覆盖: {sorted(extra_in_test)}。"
        f"需在 conftest._MODEL_RUNNER_MAP 追加 (model_id, (runner_type, extra_payload_keys)) 一行。"
    )