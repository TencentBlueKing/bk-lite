from pathlib import Path
from django.core.files.base import ContentFile
from apps.node_mgmt.models import PackageVersion
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.constants.package import PackageConstants
from apps.core.logger import node_logger as logger


def package_version_upload(_type, options):
    _os = options["os"]
    _object = options["object"]
    version = options["pk_version"]
    file_path = options["file_path"]

    if not (_object and version and file_path):
        logger.error("object, version, file_path 不能为空")
        return

    path_obj = Path(file_path)
    file_name = path_obj.name

    data = dict(
        os=_os,
        type=_type,
        object=_object,
        version=version,
        name=file_name,
        description="",
        created_by="system",
        updated_by="system",
    )

    pk_v = PackageVersion.objects.filter(
        os=_os, object=_object, version=version
    ).first()
    if pk_v:
        if version != PackageConstants.VERSION_LATEST:
            logger.warning(f"{_type} 包版本已存在!")
            return

    with path_obj.open("rb") as f:
        file_content = f.read()

    django_file = ContentFile(file_content, name=file_name)
    PackageService.upload_file(django_file, data)

    if pk_v:
        pk_v.name = file_name
        pk_v.save(update_fields=["name", "updated_at"])
        logger.info(f"{_type} latest 版本已覆盖更新")
        return data

    PackageVersion.objects.create(**data)
    return data
