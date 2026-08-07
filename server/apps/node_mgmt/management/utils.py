from pathlib import Path
from django.core.files import File
from apps.node_mgmt.models import PackageVersion
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.constants.package import PackageConstants
from apps.core.logger import node_logger as logger


def package_version_upload(_type, options):
    _os = options["os"]
    _object = options["object"]
    cpu_architecture = options.get("cpu_architecture", "")
    version = options["pk_version"]
    file_path = options["file_path"]
    force_upload = options.get("force_upload", False)

    if not (_object and version and file_path):
        logger.error("object, version, file_path 不能为空")
        return

    path_obj = Path(file_path)
    file_name = path_obj.name

    data = dict(
        os=_os,
        cpu_architecture=cpu_architecture,
        type=_type,
        object=_object,
        version=version,
        name=file_name,
        description="",
        created_by="system",
        updated_by="system",
    )

    pk_v = PackageVersion.objects.filter(os=_os, cpu_architecture=cpu_architecture, object=_object, version=version).first()
    if pk_v:
        if version != PackageConstants.VERSION_LATEST and not force_upload:
            logger.warning(f"{_type} 包版本已存在!")
            return

    # Keep controller packages on disk while JetStream uploads them in chunks.
    # These packages can exceed 1 GB, so materializing the whole file here can
    # exhaust the management process before the upload starts.
    with path_obj.open("rb") as source_file:
        PackageService.upload_file(File(source_file, name=file_name), data)

    if pk_v:
        pk_v.name = file_name
        pk_v.save(update_fields=["name", "updated_at"])
        logger.info(f"{_type} 版本对象已覆盖上传")
        return data

    PackageVersion.objects.create(**data)
    return data
