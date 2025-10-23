from pathlib import Path
from django.core.files.base import ContentFile
from apps.node_mgmt.models import PackageVersion
from apps.node_mgmt.services.package import PackageService
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

    # 检查文件是否存在
    pk_v = PackageVersion.objects.filter(os=_os, object=_object, version=version).first()
    if pk_v:
        logger.warning(f"{_type} 包版本已存在!")
        return

    with path_obj.open("rb") as f:
        file_content = f.read()

    # 创建 Django 的 ContentFile 对象
    django_file = ContentFile(file_content, name=file_name)

    # 上传文件，成功了再保存数据
    PackageService.upload_file(django_file, data)

    PackageVersion.objects.create(**data)

    return data