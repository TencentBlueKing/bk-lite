from contextlib import contextmanager
from pathlib import PurePosixPath
from tempfile import TemporaryFile

from django.conf import settings
from minio.error import S3Error

from apps.cmdb.models.config_file_version import CONFIG_FILE_BUCKET, ConfigFileVersion
from apps.cmdb.services.transfer_service import TransferError


def storage_failure_details(error):
    """只公开固定 S3 错误码与受控提示，不公开响应、对象路径或签名信息。"""
    if not isinstance(error, S3Error):
        return "", ""
    messages = {
        "NoSuchBucket": "配置文件存储桶尚未初始化，请检查存储配置及建桶权限后重试",
        "AccessDenied": "文件存储权限不足，请检查配置文件桶的访问权限",
        "InvalidAccessKeyId": "文件存储认证失败，请检查服务端存储配置",
        "SignatureDoesNotMatch": "文件存储签名校验失败，请检查服务端存储配置",
        "RequestTimeTooSkewed": "文件存储时间校验失败，请检查服务端时间",
        "NoSuchKey": "任务文件不存在，请重新提交任务",
    }
    if error.code in messages:
        return error.code, messages[error.code]
    return "OtherS3Error", "文件存储操作失败，请稍后重试或联系管理员"


class TransferFiles:
    """复用配置文件桶的客户端；直接流式传输，避免 Storage.save/open 的整文件复制。"""

    PREFIX = "transfer/"
    MAX_BYTES = 100 * 1024 * 1024

    def __init__(self, client=None):
        self.client = client if client is not None else ConfigFileVersion._meta.get_field("content").storage.client
        self._bucket_ready = False

    @classmethod
    def validate_key(cls, key):
        if not isinstance(key, str) or not key.startswith(cls.PREFIX) or ".." in PurePosixPath(key).parts or "\\" in key:
            raise TransferError("invalid_file_key", "文件不属于导入导出任务", 400)
        return key

    def put(self, key, stream):
        self.validate_key(key)
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size > self.MAX_BYTES:
            raise TransferError("file_too_large", "文件超过 100 MiB 上限", 413)
        # 流式写入也遵循配置文件 Storage 的保存期桶检查，不在服务启动时访问 MinIO。
        if settings.MINIO_BUCKET_CHECK_ON_SAVE and not self._bucket_ready:
            if not self.client.bucket_exists(CONFIG_FILE_BUCKET):
                try:
                    self.client.make_bucket(bucket_name=CONFIG_FILE_BUCKET)
                except S3Error as error:
                    if error.code != "BucketAlreadyOwnedByYou":
                        raise
            self._bucket_ready = True
        self.client.put_object(
            bucket_name=CONFIG_FILE_BUCKET,
            object_name=key,
            data=stream,
            length=size,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return {"key": key, "size": size}

    @contextmanager
    def read(self, key):
        self.validate_key(key)
        response = self.client.get_object(CONFIG_FILE_BUCKET, key)
        try:
            yield response
        finally:
            response.close()
            response.release_conn()

    @contextmanager
    def local_copy(self, key, *, max_bytes=20 * 1024 * 1024):
        with TemporaryFile(mode="w+b") as stream, self.read(key) as response:
            size = 0
            while chunk := response.read(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise TransferError("file_too_large", "上传文件超过大小上限", 413)
                stream.write(chunk)
            stream.seek(0)
            yield stream

    def delete(self, key):
        self.validate_key(key)
        self.client.remove_object(CONFIG_FILE_BUCKET, key)

    def scan(self, *, cursor="", limit=1000):
        objects = self.client.list_objects(CONFIG_FILE_BUCKET, prefix=self.PREFIX, recursive=True, start_after=cursor)
        for index, item in enumerate(objects):
            if index >= limit:
                break
            yield item


class BoundedWriter:
    """约束 ZIP 写入时的实际文件大小，不能等整个 Excel 写完才检查磁盘预算。"""

    def __init__(self, stream, limit):
        self.stream = stream
        self.limit = limit

    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise TransferError("file_too_large", "导出文件超过大小上限，请缩小范围", 413)
        return self.stream.write(data)

    def __getattr__(self, name):
        return getattr(self.stream, name)
