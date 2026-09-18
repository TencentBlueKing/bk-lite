"""vCenter 目标去重与整轮归属判定；不以根实例显示名判定采集来源。"""
import hashlib
import ipaddress
import json
import re
from contextlib import nullcontext

from django.db.models import Q

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models import CollectModels
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService


class VmwareScopeError(ValueError):
    pass


class VmwareCollectionScope:
    MODEL = "vmware_vc"
    MODELS = ("vmware_vc", "vmware_esxi", "vmware_vm", "vmware_ds")
    SOURCE_FIELD = "vc_source_key"
    CONFLICT = "此 vCenter 已有资产属于其他采集任务，无法自动接管，请使用原任务或先删除原任务"
    DUPLICATE = "此 vCenter 已配置其他采集任务，请使用已有任务或先删除重复任务"

    @staticmethod
    def _value(task, name, default=None):
        return task.get(name, default) if isinstance(task, dict) else getattr(task, name, default)

    @classmethod
    def serialize_save(cls, task, *, data=None):
        if cls._value(task, "model_id") != cls.MODEL and cls._value(data, "model_id") != cls.MODEL:
            return nullcontext()
        # 保存阶段串行化“查重 + 写任务”，不在此锁内采集或写图。
        return UniqueWriteLockService.hold(["cmdb:vmware-task-save"])

    @classmethod
    def target(cls, task):
        instances = cls._value(task, "instances") or []
        if not isinstance(instances, list) or len(instances) != 1 or not instances[0].get("inst_uuid"):
            raise VmwareScopeError("vCenter 任务必须选择一个明确的 VC 根实例")
        root = instances[0]
        address = str(root.get("ip_addr") or "").strip().rstrip(".").lower()
        if not address:
            raise VmwareScopeError("vCenter 根实例缺少采集地址")
        try:
            address = str(ipaddress.ip_address(address))
        except ValueError:
            address = address.encode("idna").decode("ascii")  # 域名规范化；不解析 DNS 或推断别名。
        credential = cls._value(task, "credential") or {}
        if isinstance(credential, list):
            credential = credential[0] if credential else {}
        try:
            port = int(credential.get("port") or 443)
        except (TypeError, ValueError) as err:
            raise VmwareScopeError("vCenter 端口必须为有效整数") from err
        if not 1 <= port <= 65535:
            raise VmwareScopeError("vCenter 端口必须在 1 至 65535 之间")
        access = (cls._value(task, "access_point") or [{}])[0]
        cloud = next((access[k] for k in ("cloud", "cloud_id", "cloud_region_id") if access.get(k) not in (None, "")), None)
        network = ("cloud", str(cloud)) if cloud is not None else ("node", str(access.get("id") or access.get("node_id") or "default"))
        source = hashlib.sha256(json.dumps([network, address, port], ensure_ascii=False).encode()).hexdigest()
        return root, address, source

    @classmethod
    def peers(cls, task):
        root, address, source = cls.target(task)
        query = Q(instances__0__inst_uuid=root["inst_uuid"]) | Q(instances__0__ip_addr__iregex=rf"^\s*{re.escape(address)}\.?\s*$")
        if ":" in address:
            # 旧任务尚无来源键，IPv6 压缩/展开形式需在候选内规范化后比较。
            query |= Q(instances__0__ip_addr__iregex=":")
        query |= Q(params__vmware_source_key=source)
        tasks = (
            CollectModels.objects.filter(model_id=cls.MODEL)
            .filter(query)
            .exclude(pk=cls._value(task, "id"))
            .only("id", "instances", "access_point", "credential", "params", "model_id")
        )
        peers = []
        for other in tasks.iterator(chunk_size=200):
            other_root, _, other_source = cls.target(other)
            if other_root["inst_uuid"] == root["inst_uuid"] or other_source == source:
                peers.append(other)
        return peers

    @classmethod
    def _owners(cls, graph, tasks):
        owners = set()
        for task in tasks:
            pk = cls._value(task, "id")
            if pk is None:
                continue
            for kind, value in (("str=", str(pk)), ("int=", int(pk))):
                rows, _ = graph.query_entity(
                    INSTANCE,
                    [
                        {"field": "model_id", "type": "str[]", "value": list(cls.MODELS)},
                        {"field": "collect_task", "type": kind, "value": value},
                    ],
                    page={"skip": 0, "limit": 1},
                    include_count=False,
                )
                if rows:
                    owners.add(str(pk))
                    break
        return owners

    @classmethod
    def validate_task(cls, task):
        if cls._value(task, "model_id") != cls.MODEL:
            return
        _, _, source = cls.target(task)
        peers = cls.peers(task)
        if peers:
            pk = cls._value(task, "id")
            existing = CollectModels.objects.filter(pk=pk).first() if pk else None
            if existing is None or cls.target(existing)[2] != source:
                raise VmwareScopeError(cls.DUPLICATE)
            with GraphClient() as graph:
                owners = cls._owners(graph, [task, *peers])
            if owners != {str(cls._value(task, "id"))}:
                raise VmwareScopeError(cls.DUPLICATE)
        return source

    @classmethod
    def prepare(cls, task, metrics, organization):
        """只读预检；返回确定的根实例。任何模型冲突都在首个写操作前拒绝。"""
        selected, _, source = cls.target(task)
        peers = cls.peers(task)
        current = str(task.id)
        orgs = {str(value) for value in (organization or [])}
        with GraphClient() as graph:
            if peers:
                owners = cls._owners(graph, [task, *peers])
                if owners != {current}:
                    if not owners:
                        raise VmwareScopeError("此 vCenter 存在重复采集任务，无法确定唯一归属，请先处理冲突")
                    raise VmwareScopeError(cls.CONFLICT if len(owners) < 2 else "此 vCenter 存在多个采集任务的混合归属，请先处理冲突")
            roots, _ = graph.query_entity(
                INSTANCE,
                [
                    {"field": "model_id", "type": "str=", "value": cls.MODEL},
                    {"field": cls.SOURCE_FIELD, "type": "str=", "value": source},
                ],
            )
            if len(roots) > 1:
                raise VmwareScopeError("此 vCenter 存在多个已纳管根实例，请先处理冲突")
            root = roots[0] if roots else graph.query_entity_by_inst_uuid(selected["inst_uuid"])
            if not root or root.get("model_id") != cls.MODEL:
                raise VmwareScopeError("所选 vCenter 根实例不存在")
            if not orgs.intersection(str(value) for value in (root.get("organization") or [])):
                raise VmwareScopeError("vCenter 根实例不在当前采集组织范围内")
            if root.get("collect_task") not in (None, "", task.id, current):
                raise VmwareScopeError(cls.CONFLICT)
            if not metrics.get(cls.MODEL):
                raise VmwareScopeError("本轮缺少 vCenter 根资产数据，未写入下属资源")
            for model, items in metrics.items():
                names = list(dict.fromkeys(item["inst_name"] for item in items)) if model != cls.MODEL else [root["inst_name"]]
                for start in range(0, len(names), 200):
                    rows, _ = graph.query_entity(
                        INSTANCE,
                        [
                            {"field": "model_id", "type": "str=", "value": model},
                            {"field": "inst_name", "type": "str[]", "value": names[start : start + 200]},
                        ],
                    )
                    for row in rows:
                        if row.get("collect_task") not in (None, "", task.id, current):
                            raise VmwareScopeError(cls.CONFLICT)
                        if not orgs.intersection(str(value) for value in (row.get("organization") or [])):
                            raise VmwareScopeError("已有 VC 资源不在当前采集组织范围内，未写入本轮数据")
        return root, source
