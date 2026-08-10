"""补丁来源的展示与删除快照模块。"""

from apps.patch_mgmt.constants import OSType, PackageManagerType, PatchSourceType
from apps.patch_mgmt.models import LinuxPatchDetail, Patch


MANUAL_SOURCE_TYPE = "manual"
SOURCE_SNAPSHOT_BATCH_SIZE = 500

_REPO_TO_SOURCE_TYPE = {
    PackageManagerType.APT: PatchSourceType.APT_REPO,
    PackageManagerType.YUM: PatchSourceType.YUM_REPO,
    PackageManagerType.DNF: PatchSourceType.DNF_REPO,
}


def _fallback_synced_source_type(patch: Patch) -> str | None:
    if not patch.last_synced_at:
        return None
    if patch.os_type == OSType.WINDOWS:
        return PatchSourceType.WSUS
    try:
        repo_type = PackageManagerType.normalize(patch.linux_detail.repo_type)
    except LinuxPatchDetail.DoesNotExist:
        return None
    return _REPO_TO_SOURCE_TYPE.get(repo_type)


def source_details_for_patch(patch: Patch) -> list[dict]:
    """返回稳定排序的当前来源和已删除来源，不向调用方暴露 ORM 关系。"""
    active_details = [
        {
            "source_id": source.id,
            "source_type": source.source_type,
            "url": source.url,
            "deleted": False,
        }
        for source in sorted(patch.sources.all(), key=lambda item: item.id)
    ]
    active_ids = {item["source_id"] for item in active_details}
    active_identity = {
        (item["source_type"], item["url"]) for item in active_details
    }
    deleted_details = []
    for value in patch.deleted_source_snapshots or []:
        if not isinstance(value, dict):
            continue
        source_id = value.get("source_id")
        source_type = str(value.get("source_type") or "")
        url = str(value.get("url") or "")
        if not source_type or source_id in active_ids:
            continue
        if (source_type, url) in active_identity:
            continue
        deleted_details.append(
            {
                "source_id": source_id,
                "source_type": source_type,
                "url": url,
                "deleted": True,
            }
        )
    if not active_details and not deleted_details and patch.last_synced_at:
        fallback_type = _fallback_synced_source_type(patch)
        if fallback_type:
            deleted_details.append(
                {
                    "source_id": None,
                    "source_type": fallback_type,
                    "url": "",
                    "deleted": True,
                }
            )
    return [*active_details, *deleted_details]


def source_type_for_patch(patch: Patch) -> str | None:
    details = source_details_for_patch(patch)
    if details:
        return details[0]["source_type"]
    if not patch.last_synced_at:
        return MANUAL_SOURCE_TYPE
    return _fallback_synced_source_type(patch)


def snapshot_deleted_source(source) -> None:
    """在删除补丁源前，把其类型和地址保存到所有关联补丁。"""
    snapshot = {
        "source_id": source.id,
        "source_type": source.source_type,
        "url": source.url,
    }
    last_id = 0
    while True:
        patches = list(
            source.patches.select_for_update()
            .filter(id__gt=last_id)
            .only("id", "deleted_source_snapshots")
            .order_by("id")[:SOURCE_SNAPSHOT_BATCH_SIZE]
        )
        if not patches:
            return
        for patch in patches:
            existing = [
                value
                for value in patch.deleted_source_snapshots or []
                if isinstance(value, dict)
                and value.get("source_id") != source.id
            ]
            patch.deleted_source_snapshots = [*existing, snapshot.copy()]
        Patch.objects.bulk_update(
            patches,
            ["deleted_source_snapshots"],
            batch_size=SOURCE_SNAPSHOT_BATCH_SIZE,
        )
        last_id = patches[-1].id
