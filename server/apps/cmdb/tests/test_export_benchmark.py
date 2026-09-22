"""显式启用的真实 FalkorDB / MinIO 导出压测；独立图 + pytest SQLite，禁止连业务关系库。"""

import json
import os
from collections import defaultdict
from time import perf_counter
from uuid import uuid4

import openpyxl
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("CMDB_EXPORT_BENCHMARK") != "1", reason="仅显式运行真实依赖压测"),
    pytest.mark.django_db(transaction=True),
]


def test_real_export_benchmark(settings, monkeypatch, tmp_path):
    from django.db import connection

    from apps.cmdb.graph.falkordb import FalkorDBClient, FalkorDBConnectionPool
    from apps.cmdb.services.instance import InstanceManage
    from apps.cmdb.services.transfer_authorization import TransferAuthorization
    from apps.cmdb.services.transfer_execution import TransferExecution
    from apps.cmdb.services.transfer_files import TransferFiles
    from apps.cmdb.services.transfer_service import TransferService
    from apps.cmdb.tasks.transfer import execute_transfer
    from apps.system_mgmt.models.role import Role
    from apps.system_mgmt.models.user import Group, User

    assert connection.vendor == "sqlite", "压测只允许 pytest 隔离的 SQLite"
    assert not FalkorDBConnectionPool()._initialized, "必须在单独 pytest 进程运行，避免复用业务图连接"
    count = int(os.environ.get("CMDB_BENCH_ROWS", "10000"))
    repeats = int(os.environ.get("CMDB_BENCH_REPEATS", "3"))
    assert 1 <= count <= 10000 and 1 <= repeats <= 3
    graph_name = "cmdb_export_bench_" + uuid4().hex
    monkeypatch.setenv("FALKORDB_DATABASE", graph_name)
    assert os.environ.get("FALKORDB_HOST"), "需注入本机 FalkorDB 连接配置"
    # 独立进程缓存，不访问/清理业务 Redis；权限逻辑、模型元数据和实例查询均保留真实实现。
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": graph_name}}
    group = Group.objects.create(name="export-benchmark")
    role = Role.objects.create(name="admin")
    owner = User.objects.create(username="export-benchmark", domain="benchmark.invalid", role_list=[role.pk], group_list=[group.pk])
    client = FalkorDBClient()
    assert client.connect()
    graph = client._graph
    assert graph.name == graph_name, "只能对本次随机测试图执行压测"
    attrs = [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
        {"attr_id": "organization", "attr_name": "组织", "attr_type": "organization"},
    ] + [{"attr_id": f"field_{i}", "attr_name": f"主机属性{i}", "attr_type": "str"} for i in range(18)]
    peer_attrs = attrs[:2]
    peer_models = ["bench_application", "bench_cluster", "bench_room"]
    associations = [f"bench_host_connect_{model}" for model in peer_models]
    peers = {model: [str(uuid4()) for _ in range(30)] for model in peer_models}
    host_uuids = [str(uuid4()) for _ in range(count)]
    keys = []
    metrics = defaultdict(float)
    calls = defaultdict(int)
    results = []

    def measure(name, function):
        def wrapped(*args, **kwargs):
            start = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                metrics[name] += perf_counter() - start
                calls[name] += 1

        return wrapped

    class MeasuredFiles(TransferFiles):
        def put(self, key, stream):
            keys.append(key)
            return measure("upload", super().put)(key, stream)

    files = MeasuredFiles()
    try:
        for model in ["bench_host"] + peer_models:
            graph.query(
                "CREATE (n:model) SET n = $properties",
                {"properties": {"model_id": model, "model_name": model, "attrs": json.dumps(attrs if model == "bench_host" else peer_attrs)}},
            )
        client.ensure_node_property_index("instance", "inst_uuid")
        client.ensure_node_property_index("instance", "model_id")
        for model, assoc in zip(peer_models, associations):
            graph.query(
                "MATCH (a:model {model_id: 'bench_host'}), (b:model {model_id: $model}) " "CREATE (a)-[r:model_association]->(b) SET r = $properties",
                {"model": model, "properties": {"model_asst_id": assoc, "src_model_id": "bench_host", "dst_model_id": model, "asst_id": "connect"}},
            )
            graph.query(
                "UNWIND $rows AS row CREATE (n:instance) SET n = row",
                {
                    "rows": [
                        {"inst_uuid": uid, "model_id": model, "inst_name": f"{model}-{i}", "organization": [group.pk]}
                        for i, uid in enumerate(peers[model])
                    ]
                },
            )
        for offset in range(0, count, 500):
            rows = [
                dict(
                    inst_uuid=uid,
                    model_id="bench_host",
                    inst_name=f"bench-host-{i:05}",
                    organization=[group.pk],
                    **{f"field_{j}": f"host-{i}-attribute-{j}-测试数据" for j in range(18)},
                )
                for i, uid in enumerate(host_uuids[offset : offset + 500], start=offset)
            ]
            graph.query("UNWIND $rows AS row CREATE (n:instance) SET n = row", {"rows": rows})
            edges = [
                {"host": row["inst_uuid"], "peer": peers[model][(offset + i + j) % 30], "association": assoc}
                for i, row in enumerate(rows)
                for model, assoc in zip(peer_models, associations)
                for j in range(3)
            ]
            graph.query(
                "UNWIND $rows AS row MATCH (a:instance {inst_uuid: row.host}), (b:instance {inst_uuid: row.peer}) "
                "CREATE (a)-[r:instance_association {model_asst_id: row.association}]->(b)",
                {"rows": edges},
            )
        assert graph.query("MATCH ()-[r:instance_association]->() RETURN count(r)").result_set[0][0] == count * 9
        monkeypatch.setattr(TransferAuthorization, "resolve", staticmethod(measure("authorization", TransferAuthorization.resolve)))
        monkeypatch.setattr(FalkorDBClient, "query_entity", measure("entity_queries", FalkorDBClient.query_entity))
        monkeypatch.setattr(FalkorDBClient, "query_export_associations", measure("relation_queries", FalkorDBClient.query_export_associations))
        monkeypatch.setattr(InstanceManage, "inst_export", staticmethod(measure("generate", InstanceManage.inst_export)))
        for relation_types in (1, 3):
            for repeat in range(repeats + 1):
                metrics.clear()
                calls.clear()
                accepted_start = perf_counter()
                context = TransferAuthorization.resolve(owner, group.pk, False, "bench_host", "export")
                task = TransferService.submit(
                    owner=owner,
                    kind="export",
                    model_id="bench_host",
                    team_id=group.pk,
                    include_children=False,
                    params={
                        "scope": "all",
                        "attr_list": [a["attr_id"] for a in attrs],
                        "association_list": associations[:relation_types],
                        "inst_uuids": [],
                    },
                    authorization=context.snapshot,
                    schema_hash=context.schema_hash,
                    idempotency_key=uuid4().hex,
                )
                accepted_seconds = perf_counter() - accepted_start
                metrics.clear()
                calls.clear()
                # 执行相同 Celery 任务函数，不投递业务 broker；队列等待和 worker 启动不计入结果。
                with monkeypatch.context() as patch:
                    patch.setattr("apps.cmdb.services.transfer_execution.TransferFiles", lambda: files)
                    started = perf_counter()
                    execute_transfer.run(str(task.pk))
                    execution_seconds = perf_counter() - started
                task.refresh_from_db()
                assert task.status == "succeeded", (task.error_code, task.message)
                assert task.summary == {"exported": count}
                record = {
                    "warmup": repeat == 0,
                    "repeat": repeat,
                    "rows": count,
                    "edges_exported": count * relation_types * 3,
                    "accept_seconds": accepted_seconds,
                    "execute_seconds": execution_seconds,
                    "seconds": dict(metrics),
                    "calls": dict(calls),
                    "xlsx_bytes": task.artifacts["result"]["size"],
                }
                # 下载与内容校验在计时外，确认不是空表/漏关联造成的虚假快结果。
                with files.local_copy(task.artifacts["result"]["key"]) as stream:
                    workbook = openpyxl.load_workbook(stream, read_only=True)
                    rows_iter = workbook.active.iter_rows(values_only=True)
                    next(rows_iter)
                    next(rows_iter)
                    header = next(rows_iter)
                    relation_columns = [header.index(assoc) for assoc in associations[:relation_types]]
                    row_count = 0
                    for row in rows_iter:
                        row_count += 1
                        for column in relation_columns:
                            assert len(row[column].split(",")) == 3
                    assert row_count == count
                    workbook.close()
                TransferExecution.validate_download(task, files)
                results.append(record)
                print("CMDB_BENCH_RESULT " + json.dumps(record), flush=True)
        (tmp_path / "results.json").write_text(json.dumps(results, indent=2))
    finally:
        try:
            for key in keys:
                files.delete(key)
        finally:
            assert os.environ["FALKORDB_DATABASE"] == graph_name and graph.name == graph_name
            graph.delete()
            client.close()
            print("CMDB_BENCH_CLEANUP graph_and_objects_deleted", flush=True)
