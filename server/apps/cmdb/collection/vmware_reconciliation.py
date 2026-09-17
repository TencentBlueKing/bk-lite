"""VC 整轮预检、根优先更新；其余图写入沿用公共采集流程。"""
from copy import deepcopy

from django.db import transaction

from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.cmdb.services.vmware_collection_scope import VmwareCollectionScope, VmwareScopeError


def rejected(metrics, error):
    return {
        model: {
            "add": {"success": [], "failed": []},
            "update": {
                "success": [],
                "failed": [{"instance_info": {"model_id": model, "inst_name": item["inst_name"]}, "error": str(error)} for item in items],
            },
            "delete": {"success": [], "failed": []},
        }
        for model, items in metrics.items()
    }


def collect_vmware(cannula):
    original = cannula.collection_metrics
    original_manual = cannula.manual
    total = sum(len(items) for items in original.values())
    try:
        _, _, source = VmwareCollectionScope.target(cannula.task)
        with transaction.atomic(), UniqueWriteLockService.hold(["cmdb:vmware-source:" + source]):
            root, source = VmwareCollectionScope.prepare(cannula.task, original, cannula.organization)
            metrics = deepcopy(original)
            for model, items in metrics.items():
                for item in items:
                    if model == VmwareCollectionScope.MODEL:
                        item["inst_name"] = root["inst_name"]
                        item[VmwareCollectionScope.SOURCE_FIELD] = source
                    elif "self_vc" in item:
                        item["self_vc"] = root["inst_name"]
                    for association in item.get("assos", []):
                        if association.get("model_id") == VmwareCollectionScope.MODEL:
                            association["inst_name"] = root["inst_name"]
            cannula.collection_metrics = {VmwareCollectionScope.MODEL: metrics.pop(VmwareCollectionScope.MODEL)}
            # 根是预先选择的已有资产，只更新；不差集删除历史重复根。
            cannula.manual = True
            result = cannula._collect_models()
            cannula.manual = original_manual
            root_result = result[VmwareCollectionScope.MODEL]
            if root_result["add"]["failed"] or root_result["update"]["failed"]:
                result.update(rejected(metrics, "vCenter 根资产更新失败，未写入下属资源"))
            else:
                cannula.collection_metrics = metrics
                result.update(cannula._collect_models())
    except VmwareScopeError as error:
        result = rejected(original, error)
    finally:
        cannula.collection_metrics = original
        cannula.manual = original_manual
    result["all"] = total
    result["__raw_data__"] = cannula.raw_data
    return result
