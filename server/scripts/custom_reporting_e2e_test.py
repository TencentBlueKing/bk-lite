#!/usr/bin/env python
"""自定义上报端到端测试脚本（真实图库 + 真实任务）。

覆盖：多任务、多条数据、多字段、身份归一化幂等、关系（建边 / 待关联 / 回填）。

特点：
- 不依赖运行中的 server——直接 django.setup() 调 ingest_service，用磁盘上最新代码。
- 使用环境里已存在的两个任务（一个 quick、一个 standard）。
- 关系需要已定义的「模型关联类型」；脚本会在两个模型间自动创建一个 n:n 关联（缺失时）。
- 每次为两个任务的凭据**重新签发 token**（会让你之前复制的 token 失效，脚本会打印新 token）。

用法（在 server/ 目录下）：
    python scripts/custom_reporting_e2e_test.py            # 跑测试
    python scripts/custom_reporting_e2e_test.py --cleanup  # 跑完后清理 e2e- 测试数据
"""
import argparse
import os
import sys

import django

# 允许从 server/scripts/ 直接运行：把 server/ 根目录加入 sys.path，使 settings 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
django.setup()

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION  # noqa: E402
from apps.cmdb.graph.drivers.graph_client import GraphClient  # noqa: E402
from apps.cmdb.services.model import ModelManage  # noqa: E402
from apps.cmdb_enterprise.custom_reporting.models import (  # noqa: E402
    CustomReportingCredential,
    CustomReportingPendingRelation,
    CustomReportingTask,
)
from apps.cmdb_enterprise.custom_reporting.services import ingest_service  # noqa: E402

PREFIX = "e2e-"
RESULTS = {"pass": 0, "fail": 0}


def check(name, ok, extra=""):
    RESULTS["pass" if ok else "fail"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {extra}")
    return ok


def issue_token(task):
    cred = CustomReportingCredential.objects.filter(task=task).first()
    if not cred:
        cred = CustomReportingCredential.objects.create(
            task=task, name=f"{task.name}-e2e", credential_type="api_token", credential_data={}
        )
    return cred.issue_token()


def instances_of(model_id):
    with GraphClient() as ag:
        items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": model_id}])
    return items


def edges_of(model_asst_id):
    with GraphClient() as ag:
        return ag.query_edge(
            INSTANCE_ASSOCIATION,
            [{"field": "model_asst_id", "type": "str=", "value": model_asst_id}],
        )


def ensure_association(src_model_id, dst_model_id, asst_id="connect"):
    """确保 src->dst 存在一个 n:n 模型关联类型；返回 model_asst_id。"""
    model_asst_id = f"{src_model_id}_{asst_id}_{dst_model_id}"
    if ModelManage.model_association_info_search(model_asst_id):
        return model_asst_id
    src = ModelManage.search_model_info(src_model_id)
    dst = ModelManage.search_model_info(dst_model_id)
    ModelManage.model_association_create(
        src_id=src["_id"],
        dst_id=dst["_id"],
        model_asst_id=model_asst_id,
        src_model_id=src_model_id,
        dst_model_id=dst_model_id,
        asst_id=asst_id,
        mapping="n:n",
    )
    print(f"  · 已创建模型关联类型: {model_asst_id} (n:n)")
    return model_asst_id


def push(token, instances, relations=None):
    payload = {"instances": instances, "relations": relations or [], "batch_metadata": {"source": "e2e"}}
    return ingest_service.ingest(token, payload, operator="e2e")["summary"]


def reset_data(a_model, b_model, tasks):
    """删除上次遗留的 e2e- 实例（连带其关联边）+ pending，保证每次运行从干净状态开始。"""
    with GraphClient() as ag:
        for mid in (a_model, b_model):
            items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": mid}])
            ids = [i["_id"] for i in items if str(i.get("inst_name", "")).startswith(PREFIX)]
            if ids:
                ag.batch_delete_entity(INSTANCE, ids)
    for t in tasks:
        CustomReportingPendingRelation.objects.filter(task=t).delete()


def discover_tasks():
    quick = next((t for t in CustomReportingTask.objects.order_by("id") if t.config.get("mode") == "quick"), None)
    std = next(
        (t for t in CustomReportingTask.objects.order_by("id") if t.config.get("mode") != "quick" and t != quick),
        None,
    )
    if not quick or not std:
        sys.exit("需要至少一个 quick 任务和一个 standard 任务，请先在界面建好。")
    return quick, std


def run():
    A, B = discover_tasks()  # A=quick, B=standard
    a_model, b_model = A.config["model_id"], B.config["model_id"]
    a_keys, b_keys = A.config["identity_keys"], B.config["identity_keys"]
    print(f"任务A(quick): {A.name} model={a_model} ids={a_keys}")
    print(f"任务B(standard): {B.name} model={b_model} ids={b_keys}")

    assoc = ensure_association(a_model, b_model)
    reset_data(a_model, b_model, [A, B])  # 清掉上次遗留，保证幂等
    tok_a, tok_b = issue_token(A), issue_token(B)
    print(f"  · A token: {tok_a}\n  · B token: {tok_b}")

    base_edges = len(edges_of(assoc))

    print("\n[场景1] A 多条 + 多字段创建")
    s = push(tok_a, [
        {"inst_name": f"{PREFIX}svc-1", "port": "8001", "owner": "ops", "env": "prod", "cpu_count": 4, "disk": "100G"},
        {"inst_name": f"{PREFIX}svc-2", "port": "8002", "owner": "dev", "env": "test", "cpu_count": 2},
        {"inst_name": f"{PREFIX}svc-3", "port": "8003", "owner": "ops", "tags": "a,b"},
    ])
    check("A 创建 3 条", s["created"] == 3, s)

    print("\n[场景2] B 多条创建")
    s = push(tok_b, [
        {"inst_name": f"{PREFIX}db-1", "version": "7.0", "role": "master"},
        {"inst_name": f"{PREFIX}db-2", "version": "7.0", "role": "slave"},
    ])
    check("B 创建 2 条", s["created"] == 2, s)

    print("\n[场景3] A 幂等：port 由 '8001' 改成数字 8001，应是更新而非新增")
    s = push(tok_a, [{"inst_name": f"{PREFIX}svc-1", "port": 8001, "owner": "ops-changed"}])
    check("幂等（123 vs '123'）→ updated=1 created=0", s["updated"] == 1 and s["created"] == 0, s)

    print("\n[场景4] 关系：引用已存在实例 → 立即建边")
    s = push(
        tok_a,
        [{"inst_name": f"{PREFIX}svc-1", "port": "8001"}],
        relations=[{
            "source": {"model_id": a_model, "identity": {"inst_name": f"{PREFIX}svc-1", "port": "8001"}},
            "target": {"model_id": b_model, "identity": {"inst_name": f"{PREFIX}db-1"}},
            "asst_id": assoc,
        }],
    )
    check("关系直接建边（pending=0）", s["pending_relations"] == 0, s)
    check("图中关联边 +1", len(edges_of(assoc)) >= base_edges + 1, f"edges={len(edges_of(assoc))}")

    print("\n[场景5] 关系：目标未上报 → 待关联，目标落地后回填")
    s = push(
        tok_a,
        [{"inst_name": f"{PREFIX}svc-2", "port": "8002"}],
        relations=[{
            "source": {"model_id": a_model, "identity": {"inst_name": f"{PREFIX}svc-2", "port": "8002"}},
            "target": {"model_id": b_model, "identity": {"inst_name": f"{PREFIX}db-new"}},
            "asst_id": assoc,
        }],
    )
    check("目标缺失 → pending_relations=1", s["pending_relations"] == 1, s)
    push(tok_b, [{"inst_name": f"{PREFIX}db-new", "version": "7.0"}])  # 目标落地
    edges_before = len(edges_of(assoc))
    push(tok_a, [{"inst_name": f"{PREFIX}svc-2", "port": "8002"}])  # 触发 backfill
    check("回填后关联边 +1", len(edges_of(assoc)) >= edges_before + 1, f"edges={len(edges_of(assoc))}")
    check(
        "pending 表已清空",
        not CustomReportingPendingRelation.objects.filter(task=A, relation_payload__target__identity__inst_name=f"{PREFIX}db-new").exists()
        or CustomReportingPendingRelation.objects.filter(task=A).count() == 0,
        "",
    )

    print("\n[校验] 图中实例落库情况")
    a_insts = [i for i in instances_of(a_model) if str(i.get("inst_name", "")).startswith(PREFIX)]
    b_insts = [i for i in instances_of(b_model) if str(i.get("inst_name", "")).startswith(PREFIX)]
    check(f"A({a_model}) e2e 实例数=3", len(a_insts) == 3, [i.get("inst_name") for i in a_insts])
    check(f"B({b_model}) e2e 实例数=3", len(b_insts) == 3, [i.get("inst_name") for i in b_insts])
    sample = next((i for i in a_insts if i.get("inst_name") == f"{PREFIX}svc-1"), {})
    fields_ok = sample.get("owner") == "ops-changed" and sample.get("env") == "prod"
    check("多字段已落库（owner/env）", fields_ok, {k: sample.get(k) for k in ("owner", "env", "cpu_count")})

    return assoc, a_model, b_model


def cleanup(assoc, a_model, b_model):
    print("\n[清理] 删除 e2e- 实例 + 关联类型 + pending")
    with GraphClient() as ag:
        for mid in (a_model, b_model):
            items, _ = ag.query_entity(INSTANCE, [{"field": "model_id", "type": "str=", "value": mid}])
            ids = [i["_id"] for i in items if str(i.get("inst_name", "")).startswith(PREFIX)]
            if ids:
                ag.batch_delete_entity(INSTANCE, ids)
                print(f"  · 删除 {mid} 实例 {len(ids)} 条")
    try:
        ModelManage.model_association_delete(ModelManage.model_association_info_search(assoc)["_id"])
        print(f"  · 删除关联类型 {assoc}")
    except Exception as e:  # noqa: BLE001
        print(f"  · 关联类型删除跳过: {e}")
    CustomReportingPendingRelation.objects.all().delete()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="跑完后清理 e2e 测试数据")
    args = parser.parse_args()

    print("=" * 60)
    print("自定义上报 E2E 测试")
    print("=" * 60)
    assoc, a_model, b_model = run()
    if args.cleanup:
        cleanup(assoc, a_model, b_model)

    print("\n" + "=" * 60)
    print(f"结果: PASS={RESULTS['pass']}  FAIL={RESULTS['fail']}")
    print("=" * 60)
    sys.exit(1 if RESULTS["fail"] else 0)


if __name__ == "__main__":
    main()
