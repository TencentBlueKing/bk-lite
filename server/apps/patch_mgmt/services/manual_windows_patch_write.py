"""手工 Windows 补丁写入模块。

对外只暴露“新增”与“编辑”两个接口，元数据、文件、就绪状态和
存储失败恢复由模块内部统一编排。
"""

from rest_framework import serializers

from apps.patch_mgmt.constants import OSType, PackageStatus
from apps.patch_mgmt.models import Patch
from apps.patch_mgmt.serializers.patch import PatchListSerializer
from apps.patch_mgmt.services.windows_package import (
    WindowsPackageError,
    WindowsPackageStorageError,
    prepare_windows_package,
    replace_failed_windows_package,
    store_windows_package,
)


class ManualWindowsPatchStorageFailure(Exception):
    def __init__(self, patch: Patch, detail: str):
        super().__init__(detail)
        self.patch = patch
        self.detail = detail


def _validated_serializer(*, metadata, context, instance=None) -> PatchListSerializer:
    serializer = PatchListSerializer(
        instance,
        data=metadata,
        context=context,
    )
    serializer.is_valid(raise_exception=True)
    os_type = serializer.validated_data.get(
        "os_type",
        getattr(instance, "os_type", None),
    )
    if os_type != OSType.WINDOWS:
        raise serializers.ValidationError(
            {"os_type": "合并文件写入仅支持手工 Windows 补丁"}
        )
    return serializer


def _prepare_file(uploaded_file):
    try:
        return prepare_windows_package(uploaded_file)
    except WindowsPackageError as exc:
        raise serializers.ValidationError({"file": str(exc)}) from exc


def create_manual_windows_patch(*, metadata, uploaded_file, context) -> Patch:
    """校验元数据和文件后创建补丁，成功返回已就绪记录。"""
    if uploaded_file is None:
        raise serializers.ValidationError({"file": "请选择 MSU 或 CAB 补丁包"})

    serializer = _validated_serializer(metadata=metadata, context=context)
    prepared = _prepare_file(uploaded_file)
    patch = serializer.save(pkg_status=PackageStatus.DOWNLOADING)
    try:
        store_windows_package(patch, uploaded_file, prepared=prepared)
    except WindowsPackageStorageError as exc:
        raise ManualWindowsPatchStorageFailure(patch, str(exc)) from exc
    return patch


def update_manual_windows_patch(
    *,
    patch: Patch,
    metadata,
    uploaded_file,
    context,
) -> Patch:
    """更新元数据；上次上传失败时，在同一次请求中替换文件。"""
    serializer = _validated_serializer(
        metadata=metadata,
        context=context,
        instance=patch,
    )

    prepared = None
    if patch.pkg_status == PackageStatus.DOWNLOAD_FAILED:
        if uploaded_file is None:
            raise serializers.ValidationError(
                {"file": "上次上传失败，请重新选择 MSU 或 CAB 补丁包"}
            )
        prepared = _prepare_file(uploaded_file)
    elif uploaded_file is not None:
        raise serializers.ValidationError(
            {"file": "仅上传失败的补丁允许替换文件"}
        )

    patch = serializer.save()
    if uploaded_file is None:
        return patch

    try:
        replace_failed_windows_package(
            patch,
            uploaded_file,
            prepared=prepared,
        )
    except WindowsPackageStorageError as exc:
        raise ManualWindowsPatchStorageFailure(patch, str(exc)) from exc
    return patch
