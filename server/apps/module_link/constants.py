from datetime import timedelta

from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT, CMDB_MONITOR_SYNC_MODEL_IDS

BATCH_LIMIT = 100
RETAIN_DAYS = 7
RETAIN_DELTA = timedelta(days=RETAIN_DAYS)
RECYCLE_BATCH_SIZE = 500

STATUS_WAITING_ACCESS = "waiting_access"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

ITEM_OK = "ok"
ITEM_ALREADY_LINKED = "already_linked"
ITEM_NOT_FOUND = "not_found"
ITEM_CONFLICT = "conflict"
ITEM_FAILED = "failed"
ITEM_SKIPPED = "skipped_model"
ITEM_NEEDS_OBJECT = "needs_object"

TASK_STATUSES = (STATUS_WAITING_ACCESS, STATUS_COMPLETED, STATUS_CANCELLED)
ITEM_STATUSES = (
    ITEM_OK,
    ITEM_ALREADY_LINKED,
    ITEM_NOT_FOUND,
    ITEM_CONFLICT,
    ITEM_FAILED,
    ITEM_SKIPPED,
    ITEM_NEEDS_OBJECT,
)

# 平台树：不是一对一台账，不走「指定对象」捷径。
PLATFORM_MODEL_IDS = frozenset(
    {
        "k8s_cluster",
        "k8s_namespace",
        "k8s_workload",
        "k8s_pod",
        "k8s_node",
        "vmware_vc",
        "aliyun_account",
        "qcloud",
        "hwcloud",
        "fusioninsight",
    }
)
PLATFORM_MODEL_PREFIXES = ("k8s_", "aliyun", "qcloud", "hwcloud", "vmware_", "fusioninsight")


def is_platform_tree_model(model_id: str | None) -> bool:
    text = str(model_id or "").strip()
    if not text:
        return False
    if text in PLATFORM_MODEL_IDS:
        return True
    return text.startswith(PLATFORM_MODEL_PREFIXES)


def builtin_object_name(model_id: str | None) -> str | None:
    return CMDB_MODEL_TO_MONITOR_OBJECT.get(str(model_id or "").strip())


def is_builtin_mapped_model(model_id: str | None) -> bool:
    return str(model_id or "").strip() in CMDB_MONITOR_SYNC_MODEL_IDS
