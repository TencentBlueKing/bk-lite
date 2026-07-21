"""
自定义 Django 字段：S3JSONField
基于 django-minio-backend，透明地将 JSON 数据存储到 S3/MinIO

设计目标：完全透明替代 JSONField
- 用户只需将 models.JSONField() 改为 S3JSONField()
- 读写操作完全不变：obj.field = {...} 和 data = obj.field
- 自动处理 S3 上传/下载和压缩/解压
"""

import copy
import gzip
import json
import uuid
from typing import Any, Optional

from django.core.files.base import ContentFile
from django.db import connections, models, transaction
from django.db.models.signals import post_save
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
    pk = instance.pk or "new"
    unique_id = uuid.uuid4().hex[:8]

    # 统一使用 .json.gz 扩展名（实际是否压缩由字段的 compressed 属性控制）
    return f"{now.year}/{now.month:02d}/{now.day:02d}/{model_name}_{pk}_{unique_id}.json.gz"


class S3JSONField(models.CharField):
    """
    S3 JSON 字段 - 完全透明替代 JSONField

    不继承 FileField（避免 Django 的默认 storage 系统干扰），而是继承 CharField
    在数据库中存储 S3 文件路径，实际数据存储在 MinIO/S3 中

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

    CLEANUP_TASKS_ATTR = "_s3json_cleanup_tasks"
    PENDING_VALUE_ATTR_TEMPLATE = "_s3json_pending_{field_name}"

    def __init__(self, bucket_name="default", compressed=True, upload_to=None, *args, **kwargs):
        """
        初始化 S3JSONField

        Args:
            bucket_name: MinIO bucket 名称
            compressed: 是否使用 gzip 压缩（默认 True，节省存储空间）
            upload_to: 上传路径生成函数（可选）
            *args, **kwargs: 传递给 CharField 的其他参数
        """
        self.bucket_name = bucket_name
        self.compressed = compressed
        self.upload_to = upload_to or s3_json_upload_path
        self.delete_previous_on_update = kwargs.pop("delete_previous_on_update", False)

        # 标记 storage 是否已经初始化
        self._minio_storage = None

        # 设置 CharField 的 max_length（存储 S3 路径）
        kwargs.setdefault("max_length", 500)

        super().__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name, **kwargs):
        """
        当字段被添加到模型类时调用
        我们需要重写这个方法来确保使用自定义的描述符
        """
        super().contribute_to_class(cls, name, **kwargs)

        # 使用自定义描述符来拦截字段访问
        setattr(cls, name, S3JSONFieldDescriptor(self))

        if self.delete_previous_on_update:
            post_save.connect(
                _handle_s3jsonfield_post_save_cleanup,
                sender=cls,
                weak=False,
                dispatch_uid=f"s3jsonfield_cleanup_{cls._meta.label_lower}_{name}",
            )

    @property
    def storage(self):
        """延迟初始化 storage - 只在实际使用时创建 MinioBackend"""
        if self._minio_storage is None:
            self._minio_storage = MinioBackend(bucket_name=self.bucket_name)
        return self._minio_storage

    def pre_save(self, model_instance, add):
        """
        在保存到数据库前调用 - 这是上传文件的正确时机

        Args:
            model_instance: 模型实例
            add: 是否是新增操作

        Returns:
            文件路径字符串（将保存到数据库）
        """
        pending_attr = self._pending_value_attr_name
        if pending_attr in model_instance.__dict__:
            file_field = model_instance.__dict__.pop(pending_attr)
            # 直接设 __dict__，不触发 descriptor 的 __set__（避免重新写入 pending 导致下次 save 覆盖数据）
            model_instance.__dict__[self.attname] = file_field

        # 获取字段当前值
        file_field = getattr(model_instance, self.attname)

        # 处理空值：如果内存中为 None 但 DB 里有路径，保留 DB 值不覆盖
        if file_field is None or file_field == "":
            db_path = model_instance.__dict__.get(self.attname)
            if isinstance(db_path, str) and db_path:
                return db_path
            return ""

        # 如果已经是文件路径（字符串），说明已经上传过了，直接返回
        if isinstance(file_field, str):
            return file_field

        # 如果是 Python 对象（list/dict），需要上传到 S3
        if isinstance(file_field, (list, dict)):
            try:
                previous_path = self._get_raw_db_value(model_instance)
                # 上传到 S3 并获取文件路径
                uploaded_path = self._upload_to_s3(model_instance, file_field)

                # 更新模型实例的字段值为文件路径
                setattr(model_instance, self.attname, uploaded_path)
                self._register_cleanup_task(model_instance, previous_path, uploaded_path)

                logger.debug(f"S3JSONField uploaded: {uploaded_path}")
                return uploaded_path

            except Exception as e:
                logger.error(f"Failed to upload JSON to S3: {e}", exc_info=True)
                raise

        # 其他情况（如 FieldFile 对象）调用父类方法
        return super().pre_save(model_instance, add)

    def _get_db_alias(self, instance):
        return getattr(getattr(instance, "_state", None), "db", None) or "default"

    def _get_raw_db_value(self, instance):
        if not self.delete_previous_on_update or not getattr(instance, "pk", None):
            return ""

        meta = instance._meta
        db_alias = self._get_db_alias(instance)
        connection = connections[db_alias]
        quote_name = connection.ops.quote_name
        query = f"SELECT {quote_name(self.column)} FROM {quote_name(meta.db_table)} WHERE {quote_name(meta.pk.column)} = %s"

        with connection.cursor() as cursor:
            cursor.execute(query, [instance.pk])
            row = cursor.fetchone()

        if not row:
            return ""

        value = row[0]
        return value if isinstance(value, str) else ""

    def _register_cleanup_task(self, instance, previous_path, current_path):
        if not self.delete_previous_on_update:
            return
        if not previous_path or not current_path or previous_path == current_path:
            return

        tasks = getattr(instance, self.CLEANUP_TASKS_ATTR, [])
        task = {
            "field_name": self.attname,
            "storage": self.storage,
            "old_path": previous_path,
            "new_path": current_path,
            "using": self._get_db_alias(instance),
        }
        tasks = [item for item in tasks if item.get("field_name") != self.attname]
        tasks.append(task)
        setattr(instance, self.CLEANUP_TASKS_ATTR, tasks)

    @property
    def _pending_value_attr_name(self):
        return self.PENDING_VALUE_ATTR_TEMPLATE.format(field_name=self.attname)

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
        json_bytes = json_str.encode("utf-8")

        # 压缩（如果启用）
        if self.compressed:
            content_bytes = gzip.compress(json_bytes, compresslevel=6)
            content_type = "application/gzip"
        else:
            content_bytes = json_bytes
            content_type = "application/json"

        # 生成文件名 - 直接调用 upload_to 函数，避免使用 generate_filename（它会触发 Django 的 default storage 查找）
        if callable(self.upload_to):
            filename = self.upload_to(instance, "data.json.gz")
        else:
            filename = s3_json_upload_path(instance, "data.json.gz")

        # 创建文件内容
        content = ContentFile(content_bytes, name=filename)

        # 上传到 S3
        saved_path = self.storage.save(filename, content)

        logger.info(
            f"Uploaded to S3: {saved_path}, "
            f"original={len(json_bytes)} bytes, "
            f"compressed={len(content_bytes)} bytes, "
            f"ratio={len(content_bytes) / len(json_bytes):.1%}"
        )

        return saved_path

    def from_db_value(self, value, expression, connection):
        if not value:
            return None
        # 返回路径字符串，延迟到 descriptor __get__ 访问时才从 S3 加载
        return value

    def to_python(self, value):
        """
        转换为 Python 对象

        处理各种输入情况：None、已加载的对象、文件路径等
        """
        if value is None or value == "":
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
        logger.info(f"[S3JSONField] Loading from S3: {file_path}")

        if not file_path:
            logger.warning(f"[S3JSONField] Empty file_path, returning None")
            return None

        try:
            # 读取文件内容
            with self.storage.open(file_path, "rb") as f:
                content_bytes = f.read()

            logger.info(f"[S3JSONField] Read {len(content_bytes)} bytes from S3")

            if not content_bytes:
                logger.warning(f"S3 file is empty: {file_path}")
                return None

            # 解压（智能检测）
            try:
                # 尝试解压
                json_bytes = gzip.decompress(content_bytes)
                logger.info(f"[S3JSONField] Decompressed {len(content_bytes)} -> {len(json_bytes)} bytes")
            except gzip.BadGzipFile:
                # 不是 gzip 文件，使用原始内容
                json_bytes = content_bytes
                logger.info(f"[S3JSONField] Not gzipped, using raw content")

            # 解析 JSON
            json_str = json_bytes.decode("utf-8")
            data = json.loads(json_str)

            logger.info(
                f"[S3JSONField] Successfully loaded from S3: {file_path}, type: {type(data)}, items: {len(data) if isinstance(data, (list, dict)) else 'N/A'}"
            )
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
        return "CharField"

    def deconstruct(self):
        """
        Django migrations 序列化支持

        确保迁移文件中的字段定义是稳定的，避免重复生成迁移
        """
        name, path, args, kwargs = super().deconstruct()

        # 添加自定义参数
        kwargs["bucket_name"] = self.bucket_name
        kwargs["compressed"] = self.compressed
        kwargs["delete_previous_on_update"] = self.delete_previous_on_update

        # 使用全局函数引用（而不是实例方法）
        # 这样 Django 在对比迁移时才能正确识别字段定义没有变化
        if "upload_to" in kwargs:
            kwargs["upload_to"] = s3_json_upload_path

        # 移除 storage 参数（会在运行时自动重建）
        kwargs.pop("storage", None)

        return name, path, args, kwargs

    def value_to_string(self, obj):
        """
        序列化字段值（用于 fixtures 和 serialization）

        返回文件路径而不是 JSON 数据
        """
        value = self.value_from_object(obj)
        if value is None or value == "":
            return ""
        return str(value) if isinstance(value, str) else ""

    def formfield(self, **kwargs):
        """
        为 Django Admin 和 Forms 提供表单字段

        使用 JSONField 的表单组件，保持用户体验一致
        """
        from django import forms

        defaults = {
            "form_class": forms.JSONField,
            "encoder": None,
            "decoder": None,
        }
        defaults.update(kwargs)

        return super().formfield(**defaults)


class S3JSONFieldDescriptor:
    """
    自定义描述符：用于拦截 S3JSONField 的字段访问

    确保在访问字段时，自动从 S3 加载数据
    """

    def __init__(self, field: S3JSONField):
        self.field = field

    def __get__(self, instance, owner):
        if instance is None:
            return self

        value = instance.__dict__.get(self.field.attname)

        if isinstance(value, str) and value:
            loaded_value = self.field._load_from_s3(value)
            if loaded_value is None:
                # S3 加载失败时保留路径，避免后续 save 把 DB 中的引用清空
                logger.warning(f"[S3JSONField] Load failed for {value}, preserving path reference")
                return None
            instance.__dict__[self.field.attname] = loaded_value
            return loaded_value

        return value

    def __set__(self, instance, value):
        """
        设置字段值时调用

        直接设置实例的属性，绕过模型的 save() 方法
        """
        if isinstance(value, (list, dict)):
            instance.__dict__[self.field._pending_value_attr_name] = copy.deepcopy(value)
            current_value = instance.__dict__.get(self.field.attname)

            if isinstance(current_value, str):
                return

        # 设置实例的属性
        instance.__dict__[self.field.attname] = value


def _handle_s3jsonfield_post_save_cleanup(sender, instance, **kwargs):
    tasks = getattr(instance, S3JSONField.CLEANUP_TASKS_ATTR, None)
    if not tasks:
        return

    remaining_tasks = []

    for task in tasks:
        old_path = task.get("old_path")
        new_path = task.get("new_path")
        storage = task.get("storage")
        using = task.get("using") or "default"
        if not old_path or not new_path or not storage:
            continue

        def _cleanup_old_object(old_path=old_path, new_path=new_path, storage=storage, model_label=sender._meta.label, pk=instance.pk):
            try:
                storage.delete(old_path)
                logger.info(
                    "Deleted previous S3JSONField object for %s(%s): %s -> %s",
                    model_label,
                    pk,
                    old_path,
                    new_path,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to delete previous S3JSONField object for %s(%s): %s, error=%s",
                    model_label,
                    pk,
                    old_path,
                    exc,
                )

        transaction.on_commit(_cleanup_old_object, using=using)

    setattr(instance, S3JSONField.CLEANUP_TASKS_ATTR, remaining_tasks)
