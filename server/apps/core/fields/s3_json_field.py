"""
自定义 Django 字段：S3JSONField
基于 django-minio-backend，透明地将 JSON 数据存储到 S3/MinIO
"""
import gzip
import json
from io import BytesIO
from typing import Any, Optional

from django.core.files.base import ContentFile
from django.db import models
from django_minio_backend import MinioBackend

from apps.core.logger import logger


class S3JSONField(models.FileField):
    """
    S3 JSON 字段

    自动将 JSON 数据压缩后存储到 MinIO/S3，读取时自动解压
    使用方式与普通字段相同，完全透明

    Example:
        class EventRawData(models.Model):
            event = models.ForeignKey(Event, on_delete=models.CASCADE)
            raw_data = S3JSONField(
                bucket_name='log-alert-raw-data',
                compressed=True,
                verbose_name='原始数据'
            )

        # 使用
        obj.raw_data = [{'log': 'test'}, {...}]  # 自动上传到 S3
        data = obj.raw_data  # 自动从 S3 读取并解压
    """

    description = "JSON data stored in S3/MinIO with optional compression"

    def __init__(self, bucket_name='default', compressed=True, *args, **kwargs):
        """
        初始化 S3JSONField

        Args:
            bucket_name: MinIO bucket 名称
            compressed: 是否使用 gzip 压缩（默认 True）
            *args, **kwargs: 传递给 FileField 的其他参数
        """
        self.bucket_name = bucket_name
        self.compressed = compressed

        # 设置 storage 为 MinioBackend
        kwargs['storage'] = MinioBackend(bucket_name=bucket_name)

        # 禁用 upload_to，我们自己控制路径
        kwargs.setdefault('upload_to', self._generate_upload_path)

        # 设置 max_length
        kwargs.setdefault('max_length', 500)

        super().__init__(*args, **kwargs)

    def _generate_upload_path(self, instance, filename):
        """
        生成上传路径
        格式: YYYY/MM/DD/{model_name}_{pk}.json.gz
        """
        from datetime import datetime
        now = datetime.now()

        model_name = instance.__class__.__name__.lower()
        pk = instance.pk or 'new'

        extension = '.json.gz' if self.compressed else '.json'

        return f"{now.year}/{now.month:02d}/{now.day:02d}/{model_name}_{pk}{extension}"

    def get_prep_value(self, value):
        """
        保存到数据库前的处理
        将 Python 对象转换为文件路径
        """
        if value is None:
            return None

        # 如果已经是文件路径（字符串），直接返回
        if isinstance(value, str):
            return super().get_prep_value(value)

        # 如果是 Python 对象（list/dict），需要序列化并上传
        try:
            # 序列化 JSON
            json_data = json.dumps(value, ensure_ascii=False)
            json_bytes = json_data.encode('utf-8')

            # 压缩（如果启用）
            if self.compressed:
                content_bytes = gzip.compress(json_bytes)
                content_type = 'application/gzip'
            else:
                content_bytes = json_bytes
                content_type = 'application/json'

            # 创建 ContentFile
            file_content = ContentFile(content_bytes)
            file_content.content_type = content_type

            return file_content

        except Exception as e:
            logger.error(f"Failed to serialize JSON for S3JSONField: {e}")
            return None

    def from_db_value(self, value, expression, connection):
        """
        从数据库读取后的处理
        将文件路径转换为 Python 对象
        """
        if value is None:
            return None

        return self._load_from_s3(value)

    def to_python(self, value):
        """
        转换为 Python 对象
        """
        if value is None or value == '':
            return None

        # 如果已经是 Python 对象
        if isinstance(value, (list, dict)):
            return value

        # 如果是文件路径，从 S3 加载
        if isinstance(value, str):
            return self._load_from_s3(value)

        return value

    def _load_from_s3(self, file_path: str) -> Optional[Any]:
        """
        从 S3 加载 JSON 数据

        Args:
            file_path: S3 文件路径

        Returns:
            解析后的 Python 对象（list 或 dict）
        """
        try:
            # 使用 storage 读取文件
            storage = self.storage

            if not storage.exists(file_path):
                logger.warning(f"S3 file not found: {file_path}")
                return None

            # 读取文件内容
            with storage.open(file_path, 'rb') as f:
                content_bytes = f.read()

            # 解压（如果是压缩的）
            if self.compressed and file_path.endswith('.gz'):
                json_bytes = gzip.decompress(content_bytes)
            else:
                json_bytes = content_bytes

            # 解析 JSON
            json_data = json_bytes.decode('utf-8')
            return json.loads(json_data)

        except Exception as e:
            logger.error(f"Failed to load JSON from S3: {file_path}, error: {e}")
            return None

    def get_internal_type(self):
        """返回内部类型"""
        return 'FileField'

    def deconstruct(self):
        """
        Django migrations 需要的解构方法
        """
        name, path, args, kwargs = super().deconstruct()

        # 添加自定义参数
        kwargs['bucket_name'] = self.bucket_name
        kwargs['compressed'] = self.compressed

        # 移除 storage（会自动重建）
        kwargs.pop('storage', None)

        return name, path, args, kwargs

