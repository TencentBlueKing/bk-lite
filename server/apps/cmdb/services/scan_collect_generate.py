"""扫描勾选行 → 按族生成采集任务。

只做分组与跳过判定；建表、凭据合并、认领 CI 在 scan_collect_task。
"""

from __future__ import annotations

from django.db import transaction

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.models.scan_model import ScanExecution, ScanHit, resolve_scan_task_credential
from apps.cmdb.services.scan_collect_task import (
    claim_collect_instances,
    collect_holding_instance,
    create_scan_collect_task,
    find_scan_generated_collect,
    merge_instance_payloads,
)
from apps.cmdb.services.scan_collect_task import normalize_scan_credential_item as _normalize_credential_item
from apps.cmdb.services.scan_collect_task import sync_scan_collect_task, uses_single_endpoint
from apps.cmdb.services.scan_identity import ensure_scan_execution_terminal
from apps.core.logger import cmdb_logger as logger

# 测试与历史导入仍走此名。
__all__ = ["ScanCollectGenerateService", "_normalize_credential_item"]


def _successful_credential_hit_task_id(host: str, credential_id: str) -> int | None:
    return (
        CollectTaskCredentialHit.objects.filter(
            object_key=f"host:{host}",
            credential_id=credential_id,
            status=CollectTaskCredentialHit.STATUS_SUCCESS,
        )
        .values_list("task_id", flat=True)
        .first()
    )


class ScanCollectGenerateService:
    @classmethod
    def generate(cls, execution: ScanExecution, hit_ids: list[int], *, operator: str = "", request=None) -> dict:
        ensure_scan_execution_terminal(execution)
        hits = list(
            ScanHit.objects.filter(
                execution=execution,
                id__in=hit_ids,
                status=ScanHit.STATUS_SUCCESS,
            ).select_related("family_run", "execution__task")
        )
        scan_task = execution.task
        results = []
        # Influx 按实例拆组；网络/主机/常规库同扫描同族合并成一张任务。
        groups: dict[tuple[str, str], dict] = {}
        recorded_task_ids = {int(hit.collect_task_id) for hit in hits if hit.collect_task_id not in (None, "")}
        live_task_ids = (
            set(CollectModels.objects.filter(pk__in=recorded_task_ids, is_system=False).values_list("pk", flat=True)) if recorded_task_ids else set()
        )

        for hit in hits:
            family_model_id = hit.family_run.model_id
            credential_id = str(hit.credential_id or "").strip()
            host = str(hit.host or "").strip()
            item = {
                "hit_id": hit.id,
                "host": host,
                "credential_id": credential_id,
                "family": family_model_id,
            }

            if not hit.inst_uuid:
                item.update({"status": "skipped", "reason": "no_ci"})
                results.append(item)
                continue
            if not credential_id:
                item.update({"status": "skipped", "reason": "no_credential"})
                results.append(item)
                continue
            if hit.collect_task_id:
                if hit.collect_task_id in live_task_ids:
                    item.update(
                        {
                            "status": "skipped",
                            "reason": "already_generated",
                            "collect_task_id": hit.collect_task_id,
                        }
                    )
                    results.append(item)
                    continue
                # 清单上的采集任务已删，清掉脏 id 后再生成。
                hit.collect_task_id = None
                hit.save(update_fields=["collect_task_id", "updated_at"])
            holding = collect_holding_instance(hit.inst_uuid)
            existing_scan = find_scan_generated_collect(
                scan_task,
                family_model_id,
                inst_uuid=hit.inst_uuid if uses_single_endpoint(family_model_id) else None,
            )
            if holding is not None and (existing_scan is None or existing_scan.id != holding.id):
                item.update({"status": "skipped", "reason": "already_on_collect"})
                results.append(item)
                continue
            hit_task_id = _successful_credential_hit_task_id(host, credential_id)
            if hit_task_id is not None:
                if existing_scan is None or existing_scan.id != hit_task_id:
                    item.update({"status": "skipped", "reason": "credential_already_hit"})
                    results.append(item)
                    continue

            credential_item = resolve_scan_task_credential(scan_task, family_model_id, credential_id)
            if not credential_item:
                item.update({"status": "failed", "reason": "credential_not_found"})
                results.append(item)
                continue

            group_inst = hit.inst_uuid if uses_single_endpoint(family_model_id) else ""
            group = groups.setdefault(
                (family_model_id, group_inst),
                {
                    "family_model_id": family_model_id,
                    "credential_items": {},
                    "hosts": [],
                    "inst_uuids": [],
                    "instances": [],
                    "host": host,
                    "port": hit.port or 0,
                    "items": [],
                },
            )
            group["credential_items"][credential_id] = credential_item
            group["hosts"].append(host)
            group["inst_uuids"].append(hit.inst_uuid)
            group["instances"] = merge_instance_payloads(
                group["instances"],
                [{"inst_uuid": hit.inst_uuid, "model_id": hit.cmdb_model_id or family_model_id}],
            )
            group["items"].append(item)

        for group in groups.values():
            existing = find_scan_generated_collect(
                scan_task,
                group["family_model_id"],
                inst_uuid=group["inst_uuids"][0] if uses_single_endpoint(group["family_model_id"]) else None,
            )
            credential_items = list(group["credential_items"].values())
            try:
                with transaction.atomic():
                    if existing is not None:
                        collect = sync_scan_collect_task(
                            existing,
                            scan_task=scan_task,
                            instances=group["instances"] or None,
                            credentials=credential_items,
                            request=request,
                        )
                        status = "appended"
                    else:
                        collect = create_scan_collect_task(
                            scan_task=scan_task,
                            family_model_id=group["family_model_id"],
                            credential_items=credential_items,
                            request=request,
                            instances=group["instances"] or None,
                            host=group["host"],
                            port=group["port"],
                        )
                        status = "created"
                    claim_collect_instances(collect, group["inst_uuids"])
                for index, item in enumerate(group["items"]):
                    item_status = status
                    if status == "created" and index > 0:
                        item_status = "appended"
                    item.update(
                        {
                            "status": item_status,
                            "collect_task_id": collect.id,
                            "collect_task_name": collect.name,
                        }
                    )
                    results.append(item)
                hit_ids_in_group = [row["hit_id"] for row in group["items"] if row.get("hit_id")]
                if hit_ids_in_group:
                    ScanHit.objects.filter(id__in=hit_ids_in_group).update(collect_task_id=collect.id)
            except Exception as exc:
                logger.exception(
                    "[ScanCollectGenerate] 生成失败 family=%s",
                    group["family_model_id"],
                )
                for item in group["items"]:
                    item.update({"status": "failed", "reason": str(exc)})
                    results.append(item)

        created = sum(1 for row in results if row.get("status") == "created")
        appended = sum(1 for row in results if row.get("status") == "appended")
        skipped = sum(1 for row in results if row.get("status") == "skipped")
        failed = sum(1 for row in results if row.get("status") == "failed")
        return {
            "execution_id": execution.id,
            "created": created,
            "appended": appended,
            "skipped": skipped,
            "failed": failed,
            "items": results,
        }
