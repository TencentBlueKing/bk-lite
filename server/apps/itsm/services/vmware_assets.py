"""将已交付的虚拟机与同源采集资产匹配；仅按需读取 CMDB。"""

import hashlib
import json
from collections import defaultdict
from urllib.parse import urlencode
from uuid import UUID

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models import CollectModels
from apps.cmdb.views.instance import InstanceViewSet
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.backends import _normalize_group_ids


def _valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


def resolve_cmdb_assets(request, plan, machines):
    root_uuid, team = plan.get("vc_instance_uuid"), plan.get("team_id")
    if not _valid_uuid(root_uuid) or type(team) is not int or team not in _normalize_group_ids(request.user.group_list):
        return {}
    wanted = {}
    for delivery_id, item in machines.items():
        payload, receipt = item.get("request") or {}, item.get("receipt") or {}
        if payload.get("delivery_id") != delivery_id or not _valid_uuid(receipt.get("vm_uuid")) or not receipt.get("vm_id"):
            continue
        marker = "BK-Lite-ITSM:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        wanted[delivery_id] = (receipt["vm_id"], marker)
    if not wanted or not InstanceViewSet._is_model_visible("vmware_vm"):
        return {}
    org = {"field": "organization", "type": "list[]", "value": [team]}
    with GraphClient() as graph:
        roots, _ = graph.query_entity(
            INSTANCE,
            [org, {"field": "inst_uuid", "type": "str=", "value": root_uuid}, {"field": "model_id", "type": "str=", "value": "vmware_vc"}],
            page={"skip": 0, "limit": 2},
            include_count=False,
            fields=["inst_uuid", "collect_task", "vc_source_key"],
        )
        if len(roots) != 1:
            return {}
        root = roots[0]
        owner, source = str(root.get("collect_task") or ""), root.get("vc_source_key")
        if not owner.isdecimal() or not source:
            return {}
        teams = (
            CollectModels.objects.filter(
                pk=int(owner), domain=request.user.domain, model_id="vmware_vc", instances__0__inst_uuid=root_uuid, params__vmware_source_key=source
            )
            .values_list("team", flat=True)
            .first()
        )
        if team not in _normalize_group_ids(teams or []):
            return {}
        candidates = defaultdict(dict)
        resource_ids = sorted({key[0] for key in wanted.values()})
        for kind, value in (("int=", int(owner)), ("str=", owner)):
            rows, _ = graph.query_entity(
                INSTANCE,
                [
                    org,
                    {"field": "model_id", "type": "str=", "value": "vmware_vm"},
                    {"field": "collect_task", "type": kind, "value": value},
                    {"field": "resource_id", "type": "str[]", "value": resource_ids},
                ],
                include_count=False,
            )
            for row in rows:
                candidates[row["resource_id"]][row.get("inst_uuid")] = row
    result = {}
    for delivery_id, (resource_id, marker) in wanted.items():
        matches = candidates.get(resource_id, {})
        if len(matches) != 1:
            continue
        asset_id, row = next(iter(matches.items()))
        if (
            not _valid_uuid(asset_id)
            or row.get("annotation") != marker
            or CmdbPermissionMixin().require_instance_permission(request, row) is not None
        ):
            continue
        result[delivery_id] = "/cmdb/assetData/detail/baseInfo?" + urlencode(
            {"model_id": "vmware_vm", "inst_uuid": asset_id, "inst_name": row.get("inst_name") or resource_id}
        )
    return result
