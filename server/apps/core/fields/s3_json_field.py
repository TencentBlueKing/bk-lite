"""
自定义 Django 字段：S3JSONField
基于 django-minio-backend，透明地将 JSON 数据存储到 S3/MinIO

设计目标：完全透明替代 JSONField
- 用户只需将 models.JSONField() 改为 S3JSONField()
- 读写操作完全不变：obj.field = {...} 和 data = obj.field
- 自动处理 S3 上传/下载和压缩/解压
"""
import gzip
import json
import uuid
from typing import Any, Optional

from django.core.files.base import ContentFile
from django.db import models
from django_minio_backend import MinioBackend

from apps.core.logger import logger


def s3_json_upload_path(instance, filename):
    """
    全局函数：生成 S3 上传路径

    必须是模块级别的全局函数，而不是类方法
    这样 Django migrations 才能正确序列化和引用

    格式: YYYY/MM/DD/{model_name}_{pk}_{uuid}.json.gz
    """
    from datetime import datetime
    now = datetime.now()

    model_name = instance.__class__.__name__.lower()
    pk = instance.pk or 'new'
    unique_id = uuid.uuid4().hex[:8]

    # 统一使用 .json.gz 扩展名（实际是否压缩由字段的 compressed 属性控制）
    return f"{now.year}/{now.month:02d}/{now.day:02d}/{model_name}_{pk}_{unique_id}.json.gz"


class S3JSONField(models.FileField):
    """
    S3 JSON 字段 - 完全透明替代 JSONField

    使用示例（替换 JSONField）：
        # 原来的代码
        class EventRawData(models.Model):
            data = models.JSONField(verbose_name='原始数据')

        # 替换为 S3JSONField（其他代码不变）
        class EventRawData(models.Model):
            data = S3JSONField(
                bucket_name='log-alert-raw-data',
                compressed=True,
                verbose_name='原始数据'
            )

        # 使用方式完全相同
        obj.data = [{'log': 'test'}, {...}]  # 自动上传到 S3
        obj.save()

        data = obj.data  # 自动从 S3 读取并解压
    """

    description = "JSON data stored in S3/MinIO with optional compression (transparent JSONField replacement)"

    def __init__(self, bucket_name='default', compressed=True, *args, **kwargs):
        """
        初始化 S3JSONField

        Args:
            bucket_name: MinIO bucket 名称
            compressed: 是否使用 gzip 压缩（默认 True，节省存储空间）
            *args, **kwargs: 传递给 FileField 的其他参数
        """
        self.bucket_name = bucket_name
        self.compressed = compressed

        # 延迟创建 storage，避免在 Django 启动时就要求 MinIO 可用
        self._storage = None

        # 使用全局函数作为 upload_to，确保 migrations 兼容性
        kwargs.setdefault('upload_to', s3_json_upload_path)
        kwargs.setdefault('max_length', 500)

        super().__init__(*args, **kwargs)

    @property
    def storage(self):
        """延迟初始化 storage"""
        if self._storage is None:
            self._storage = MinioBackend(bucket_name=self.bucket_name)
        return self._storage

    @storage.setter
    def storage(self, value):
        self._storage = value

    def pre_save(self, model_instance, add):
        """
        在保存到数据库前调用 - 这是上传文件的正确时机

        Args:
            model_instance: 模型实例
            add: 是否是新增操作

        Returns:
            文件路径字符串（将保存到数据库）
        """
        # 获取字段当前值
        file_field = getattr(model_instance, self.attname)

        # 处理空值
        if file_field is None or file_field == '':
            return ''

        # 如果已经是文件路径（字符串），说明已经上传过了，直接返回
        if isinstance(file_field, str):
            return file_field

        # 如果是 Python 对象（list/dict），需要上传到 S3
        if isinstance(file_field, (list, dict)):
            try:
                # 上传到 S3 并获取文件路径
                uploaded_path = self._upload_to_s3(model_instance, file_field)

                # 更新模型实例的字段值为文件路径
                setattr(model_instance, self.attname, uploaded_path)

                logger.debug(f"S3JSONField uploaded: {uploaded_path}")
                return uploaded_path

            except Exception as e:
                logger.error(f"Failed to upload JSON to S3: {e}", exc_info=True)
                raise

        # 其他情况（如 FieldFile 对象）调用父类方法
        return super().pre_save(model_instance, add)

    def _upload_to_s3(self, instance, json_data) -> str:
        """
        将 JSON 数据序列化、压缩并上传到 S3

        Args:
            instance: 模型实例
            json_data: Python 对象（list 或 dict）

        Returns:
            S3 文件路径
        """
        # 序列化 JSON
        json_str = json.dumps(json_data, ensure_ascii=False, indent=None)
        json_bytes = json_str.encode('utf-8')

        # 压缩（如果启用）
        if self.compressed:
            content_bytes = gzip.compress(json_bytes, compresslevel=6)
            content_type = 'application/gzip'
        else:
            content_bytes = json_bytes
            content_type = 'application/json'

        # 生成文件名
        filename = self.generate_filename(instance, "data.json.gz")

        # 创建文件内容
        content = ContentFile(content_bytes, name=filename)

        # 上传到 S3
        saved_path = self.storage.save(filename, content)

        logger.info(
            f"Uploaded to S3: {saved_path}, "
            f"original={len(json_bytes)} bytes, "
            f"compressed={len(content_bytes)} bytes, "
            f"ratio={len(content_bytes)/len(json_bytes):.1%}"
        )

        return saved_path

    def from_db_value(self, value, expression, connection):
        """
        从数据库读取后的处理 - 透明地从 S3 加载 JSON

        这是实现透明替换的关键：用户读取字段时，自动从 S3 下载并解析
        """
        if not value:
            return None

        return self._load_from_s3(value)

    def to_python(self, value):
        """
        转换为 Python 对象

        处理各种输入情况：None、已加载的对象、文件路径等
        """
        if value is None or value == '':
            return None

        # 如果已经是 Python 对象（缓存的数据）
        if isinstance(value, (list, dict)):
            return value

        # 如果是文件路径字符串，从 S3 加载
        if isinstance(value, str):
            return self._load_from_s3(value)

        return value

    def _load_from_s3(self, file_path: str) -> Optional[Any]:
        """
        从 S3 加载、解压并解析 JSON 数据

        Args:
            file_path: S3 文件路径

        Returns:
            Python 对象（list 或 dict）
        """
        if not file_path:
            return None

        try:
            # 检查文件是否存在
            if not self.storage.exists(file_path):
                logger.warning(f"S3 file not found: {file_path}")
                return None

            # 读取文件内容
            with self.storage.open(file_path, 'rb') as f:
                content_bytes = f.read()

            if not content_bytes:
                logger.warning(f"S3 file is empty: {file_path}")
                return None

            # 解压（智能检测）
            try:
                # 尝试解压
                json_bytes = gzip.decompress(content_bytes)
            except gzip.BadGzipFile:
                # 不是 gzip 文件，使用原始内容
                json_bytes = content_bytes

            # 解析 JSON
            json_str = json_bytes.decode('utf-8')
            data = json.loads(json_str)

            logger.debug(f"Loaded from S3: {file_path}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in S3 file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load from S3 {file_path}: {e}", exc_info=True)
            return None

    def get_prep_value(self, value):
        """
        准备要保存到数据库的值

        注意：实际的 S3 上传在 pre_save() 中完成
        这里只是做基本的类型检查和转换
        """
        if value is None:
            return None

        # 如果是文件路径，直接返回
        if isinstance(value, str):
            return value

        # 如果是 Python 对象，返回 None（实际上传会在 pre_save 中完成）
        # 这里不能直接上传，因为可能还没有 instance.pk
        if isinstance(value, (list, dict)):
            return None

        return super().get_prep_value(value)

    def get_internal_type(self):
        """返回内部字段类型"""
        return 'FileField'

    def deconstruct(self):
        """
        Django migrations 序列化支持

        确保迁移文件中的字段定义是稳定的，避免重复生成迁移
        """
        name, path, args, kwargs = super().deconstruct()

        # 添加自定义参数
        kwargs['bucket_name'] = self.bucket_name
        kwargs['compressed'] = self.compressed

        # 使用全局函数引用（而不是实例方法）
        # 这样 Django 在对比迁移时才能正确识别字段定义没有变化
        if 'upload_to' in kwargs:
            kwargs['upload_to'] = s3_json_upload_path

        # 移除 storage 参数（会在运行时自动重建）
        kwargs.pop('storage', None)

        return name, path, args, kwargs

    def value_to_string(self, obj):
        """
        序列化字段值（用于 fixtures 和 serialization）

        返回文件路径而不是 JSON 数据
        """
        value = self.value_from_object(obj)
        if value is None or value == '':
            return ''
        return str(value) if isinstance(value, str) else ''

    def formfield(self, **kwargs):
        """
        为 Django Admin 和 Forms 提供表单字段

        使用 JSONField 的表单组件，保持用户体验一致
        """
        from django import forms

        defaults = {
            'form_class': forms.JSONField,
            'encoder': None,
            'decoder': None,
        }
        defaults.update(kwargs)

        return super().formfield(**defaults)
