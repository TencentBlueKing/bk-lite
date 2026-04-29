import re
from typing import AsyncGenerator

from django.core.files.base import ContentFile
from apps.node_mgmt.utils.s3 import (
    upload_file_to_s3,
    download_file_by_s3,
    delete_s3_file,
    list_s3_files,
    stream_download_file_by_s3,
)
from asgiref.sync import async_to_sync
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class PackageService:
    @staticmethod
    def normalize_upload_cpu_architecture(cpu_architecture: str | None) -> str:
        normalized = normalize_cpu_architecture(cpu_architecture)
        return normalized or "x86_64"

    @staticmethod
    def resolve_package_by_architecture(package_seed_id: int, cpu_architecture: str):
        package_obj = PackageVersion.objects.filter(id=package_seed_id).first()
        if not package_obj:
            return None

        normalized_arch = normalize_cpu_architecture(cpu_architecture)
        if not normalized_arch:
            return package_obj

        resolved = PackageVersion.objects.filter(
            type=package_obj.type,
            os=package_obj.os,
            object=package_obj.object,
            version=package_obj.version,
            cpu_architecture=normalized_arch,
        ).first()
        if resolved:
            return resolved

        return PackageVersion.objects.filter(
            type=package_obj.type,
            os=package_obj.os,
            object=package_obj.object,
            version=package_obj.version,
            cpu_architecture="",
        ).first()

    @staticmethod
    def build_file_path(package_obj) -> str:
        arch = getattr(package_obj, "cpu_architecture", "") or "generic"
        return f"{package_obj.os}/{arch}/{package_obj.object}/{package_obj.version}/{package_obj.name}"

    @staticmethod
    def parse_package_info(filename: str):
        """从包文件名中解析版本号"""
        # 移除常见文件扩展名（如果存在）
        ext_name = ""
        name_without_ext = filename
        for ext in PackageConstants.SUPPORTED_EXTENSIONS:
            if filename.endswith(ext):
                ext_name = ext
                name_without_ext = filename[: -len(ext)]
                break

        # 匹配版本号
        match = re.match(PackageConstants.VERSION_PATTERN, name_without_ext)

        if not match:
            return None

        object_name = match.group(1)
        version = match.group(2)
        # 重新构建去掉版本号的文件名
        name_without_version = object_name + ext_name

        return {
            "object": object_name,
            "version": version,
            "name_without_version": name_without_version,
            "raw_filename": filename,
        }

    @staticmethod
    def validate_package(filename: str, expected_type: str, expected_os: str, expected_object: str, expected_arch: str = ""):
        """校验上传的包是否合格"""
        # 解析文件名
        parsed_info = PackageService.parse_package_info(filename)
        if not parsed_info:
            return False, PackageConstants.ERROR_MSG_VERSION_NOT_FOUND, None

        # 获取期望的包名称
        expected_package_name = expected_object
        if expected_type == PackageConstants.TYPE_COLLECTOR:
            collector = Collector.objects.filter(name=expected_object, node_operating_system=expected_os).first()
            if collector and collector.package_name:
                expected_package_name = collector.package_name
        elif expected_type == PackageConstants.TYPE_CONTROLLER:
            expected_package_name = PackageConstants.CONTROLLER_DEFAULT_PACKAGE_NAME

        # 校验包名称是否匹配
        parsed_obj = parsed_info["object"].lower()
        expected_obj = expected_package_name.lower()
        if parsed_obj != expected_obj and expected_obj not in parsed_obj:
            type_name = PackageConstants.TYPE_NAME_MAP.get(expected_type, expected_type)
            error_msg = PackageConstants.ERROR_MSG_TYPE_MISMATCH.format(
                type_name=type_name,
                expected=expected_package_name,
                actual=parsed_info["object"],
            )
            return False, error_msg, None

        # 检查版本是否已存在
        normalized_arch = PackageService.normalize_upload_cpu_architecture(expected_arch)
        existing_package = PackageVersion.objects.filter(
            os=expected_os,
            cpu_architecture=normalized_arch,
            object=expected_object,
            version=parsed_info["version"],
        ).first()

        if existing_package:
            if parsed_info["version"] == PackageConstants.VERSION_LATEST:
                parsed_info["existing_package"] = existing_package
                return True, "", parsed_info
            error_msg = PackageConstants.ERROR_MSG_VERSION_EXISTS.format(version=parsed_info["version"])
            return False, error_msg, None

        return True, "", parsed_info

    @staticmethod
    def upload_file(file: ContentFile, data):
        arch = data.get("cpu_architecture") or "generic"
        s3_file_path = f"{data['os']}/{arch}/{data['object']}/{data['version']}/{data['name']}"
        async_to_sync(upload_file_to_s3)(file, s3_file_path)

    @staticmethod
    def download_file(package_obj):
        s3_file_path = PackageService.build_file_path(package_obj)
        return async_to_sync(download_file_by_s3)(s3_file_path)

    @staticmethod
    def delete_file(package_obj):
        s3_file_path = PackageService.build_file_path(package_obj)
        async_to_sync(delete_s3_file)(s3_file_path)

    @staticmethod
    def list_files():
        files = async_to_sync(list_s3_files)()
        files = [
            {
                "name": file.name,
                "nuid": file.nuid,
                "description": file.description,
                "deleted": file.deleted,
            }
            for file in files
        ]
        return files

    @staticmethod
    async def stream_download_file(
        package_obj,
    ) -> AsyncGenerator[tuple[bytes, str, int], None]:
        s3_file_path = PackageService.build_file_path(package_obj)
        async for chunk, filename, total_size in stream_download_file_by_s3(s3_file_path):
            yield chunk, filename, total_size

    @staticmethod
    def download_file_streaming(package_obj) -> tuple:
        """
        流式下载文件，返回 (generator, filename)。
        使用临时文件缓冲，避免大文件内存堆积。
        """
        import tempfile
        from apps.rpc.jetstream import JetStreamService

        s3_file_path = PackageService.build_file_path(package_obj)

        async def _download_to_tempfile():
            jetstream = JetStreamService()
            await jetstream.connect()
            try:
                info = await jetstream.object_store.get_info(s3_file_path)
                filename = info.description or package_obj.name
                tmp = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
                await jetstream.object_store.get(s3_file_path, writeinto=tmp)
                tmp.seek(0)
                return tmp, filename
            finally:
                await jetstream.close()

        tmp_file, filename = async_to_sync(_download_to_tempfile)()

        def file_chunk_generator(f, chunk_size=1024 * 1024):
            try:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                f.close()
                import os

                os.unlink(f.name)

        return file_chunk_generator(tmp_file), filename


# from config.components.temp_upload import FILE_UPLOAD_TEMP_DIR
# from django.core.files.storage import default_storage

# class PackageService:
#     @staticmethod
#     def upload_file(file: ContentFile, data):
#         # 上传文件到S3
#         s3_file_path = f"{data['os']}/{data['object']}/{data['version']}/{data['name']}"
#         upload_file_to_s3(file, s3_file_path)
#
#         # local_file_path = f"{FILE_UPLOAD_TEMP_DIR}/{package_obj.name}"
#         #
#         # # 接收文件到指定目录
#         # default_storage.save(local_file_path, ContentFile(file.read()))
#         # s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         # # 从指定目录上传文件到s3
#         # upload_file_to_s3(local_file_path, s3_file_path)
#         #
#         # # 删除临时文件
#         # if default_storage.exists(local_file_path):
#         #     default_storage.delete(local_file_path)
#
#     @staticmethod
#     def download_file(package_obj):
#         s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         return download_file_by_s3(s3_file_path)
#
#     @staticmethod
#     def delete_file(package_obj):
#         s3_file_path = f"{package_obj.os}/{package_obj.object}/{package_obj.version}/{package_obj.name}"
#         # 删除文件
#         delete_s3_file(s3_file_path)
