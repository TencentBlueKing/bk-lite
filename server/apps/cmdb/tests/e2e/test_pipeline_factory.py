"""基于工厂的 fixture_driven e2e 参数化模板。

v4 Phase 2.1 任务:把 4 个现有对象(influxdb/mysql/nginx/redis)用 `load_runner_plugin_for_model_id` 工厂
+ `pytest.mark.parametrize` 跑通,作为后续 23 个对象的可复用模板。

每个对象跑 3 层验证:
  1) 契约层:fixture 命中 01_stargazer_raw schema
  2) 流水线层:cmdb_result[<model_id>] 至少 1 个实例
  3) 字段对齐层:实例关键字段与 04_expected_cmdb_result.json 子集一致

+ inst_name 规则 {ip}-{model_id}-{port} 兜底校验
"""
import json
from pathlib import Path

import jsonschema
import pytest

E2E_ROOT = Path(__file__).parent


def _read(rel_path: str):
    with open(E2E_ROOT / rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


# v3+ 已有 fixture + 04_expected 的对象
# 注:每个对象的 port 字段名可能不同(influxdb/redis 用 "port",nginx stargazer raw 用 "listen_port")
# 用 (model_id, port_field_name) 元组描述差异
FACTORY_COVERED_MODEL_IDS = [
    "influxdb",   # port="18086" from stargazer raw["port"]
    "mysql",      # port="13306"
    "nginx",      # port from stargazer raw["listen_port"]
    "redis",      # port="16379" from stargazer raw["port"]
    "kafka",      # port="9092" from stargazer raw["port"](middleware runner)
    "tomcat",     # port="8080" from stargazer raw["port"](middleware runner,extra_payload_keys={"result": True})
    "elasticsearch", # port="9200",db 平铺;fixture 目录用 elasticsearch,task 内部用 model_id="es"(plugin supported_model_id).PipelineFactory 会映射到 "es"。
    "postgresql",   # port="15432",db 平铺;plugin inst_name 短名 "pg" 而非 model_id(apps/cmdb/collection/plugins/community/db/postgresql.py)
    "mongodb",    # port="27017",db 平铺(形态 B,raw_stdout 自身即平铺 dict),plugin=apps/cmdb/collection/plugins/community/db/mongodb.py
    "haproxy",    # port="80&8404" 多端口拼接字符串(middleware runner,extra_payload_keys={"result": True});raw_stdout 走公共契约 raw_stdout_envelope_b 形态(无 bk_inst_name/bk_obj_id);plugin=apps/cmdb/collection/plugins/community/middleware/haproxy.py
    "zookeeper",  # port="2181",middleware runner result=True;plugin 字段集对齐 ZookeeperCollectionPlugin.field_mapping
    "rabbitmq",   # port="5672",middleware runner result=True;raw_stdout 是形态 B(平铺);plugin=apps/cmdb/collection/plugins/community/middleware/rabbitmq.py
]  


def _extract_raw_items(stargazer_raw: dict, model_id: str) -> dict:
    """从 stargazer fixture 抽出 plugin 入参形态。

    三种形态兼容:
    - {"raw_stdout": {"result": {<model_id>: [items]}}}  ← mysql/redis/influxdb 形态
    - {"raw_stdout": {<fields 平铺>}}  ← nginx 形态(raw_stdout 自身就是 dict)
    - 直接 dict  ← 测试用 01_raw_collector.json
    """
    if "raw_stdout" not in stargazer_raw:
        # 直接 dict(测试用人造 raw 形态,如 01_raw_collector.json)
        return stargazer_raw
    raw_stdout = stargazer_raw["raw_stdout"]
    # mysql/redis/influxdb 形态:raw_stdout["result"][model_id] = [items]
    if isinstance(raw_stdout, dict) and "result" in raw_stdout:
        result = raw_stdout["result"]
        if isinstance(result, dict) and model_id in result:
            items = result[model_id]
            if isinstance(items, list) and items:
                return items[0]
            if isinstance(items, dict):
                return items
    # nginx 形态:raw_stdout 自身就是平铺 dict
    return raw_stdout


def _extract_port(raw_items: dict) -> str:
    """从 raw_items 抽出 port(优先 port 字段,fallback listen_port)。"""
    for k in ("port", "listen_port"):
        if k in raw_items:
            return str(raw_items[k])
    raise KeyError(f"raw_items 缺 port / listen_port: keys={list(raw_items.keys())}")


@pytest.mark.django_db
@pytest.mark.parametrize("model_id", FACTORY_COVERED_MODEL_IDS)
def test_pipeline_fixture_driven_via_factory(monkeypatch, model_id, runner_plugin_factory):
    """基于工厂的 fixture_driven 流水线(3 层验证)。"""
    # 工厂拿 runner / plugin / extra_payload_keys
    runner_cls, plugin_cls, extra_payload_keys = runner_plugin_factory(model_id)

    # 读 fixture / schema
    stargazer_raw = _read(f"fixtures/{model_id}/01_stargazer_raw.json")
    raw_schema = _read(f"schemas/{model_id}/01_stargazer_raw.schema.json")
    expected_doc = _read(f"fixtures/{model_id}/04_expected_cmdb_result.json")
    inst_schema = _read(f"schemas/{model_id}/04_cmdb_instance.schema.json")

    # 1) 契约层
    jsonschema.validate(stargazer_raw, raw_schema)

    # 抽 raw_items
    raw_items = _extract_raw_items(stargazer_raw, model_id)
    ip_addr = raw_items["ip_addr"]
    port = _extract_port(raw_items)

    # pipeline 实际使用的 model_id:当 stargazer 落盘的 model_id 与 plugin supported_model_id
    # 不一致时(如 stargazer 用 'elasticsearch',plugin 用 'es'),expected_doc.pipeline_model_id 显式声明。
    # 未声明时默认用 parametrize 的 model_id(即 fixture 目录名)。
    pipeline_model_id = expected_doc.get("pipeline_model_id", model_id)

    # 2) 流水线层
    from apps.cmdb.tests.e2e import pipeline
    run = pipeline.run_full_pipeline_generic(
        raw_items=raw_items,
        runner_cls=runner_cls,
        plugin_cls=plugin_cls,
        model_id=pipeline_model_id,
        task_id=20000 + hash(model_id) % 1000,
        instances=[{"inst_name": f"{pipeline_model_id}-factory-01", "ip_addr": ip_addr}],
        extra_payload_keys=extra_payload_keys,
        monkeypatch=monkeypatch,
    )
    instances = run["cmdb_result"][pipeline_model_id]
    assert len(instances) >= 1, f"{model_id}: 工厂流水线应至少产出 1 个实例"

    # 3) 字段对齐层(expected_subset_fixture_driven 是 stargazer raw 期望值)
    inst = instances[0]
    jsonschema.validate(inst, inst_schema)
    expected_subset_key = (
        "expected_instance_subset_fixture_driven"
        if "expected_instance_subset_fixture_driven" in expected_doc
        else "expected_instance_subset"
    )
    expected_subset = expected_doc[expected_subset_key]
    for field, want in expected_subset.items():
        got = inst.get(field)
        assert got == want, f"{model_id} 字段 {field}：期望 {want!r}，实际 {got!r}"

    # inst_name 规则 {ip}-{name_token}-{port} 兜底校验
    # name_token 优先取 expected_doc.inst_name_alias(plugin 自定义短名,如 postgresql→"pg");
    # 未声明则用 pipeline_model_id(plugin supported_model_id,如 elasticsearch→"es")。
    name_token = expected_doc.get("inst_name_alias", pipeline_model_id)
    assert inst["inst_name"] == f"{ip_addr}-{name_token}-{port}", (
        f"{model_id} inst_name 规则违反：{inst['inst_name']!r} != {ip_addr}-{name_token}-{port}"
    )