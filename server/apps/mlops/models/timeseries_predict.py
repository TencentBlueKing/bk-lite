
from django.db import models
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.fields import S3JSONField
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.models.data_points_features_info import DataPointFeaturesInfo


class TimeSeriesPredictDataset(MaintainerInfo, TimeInfo):
    """时间序列预测数据集"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "时间序列预测数据集"
        verbose_name_plural = "时间序列预测数据集"

    def __str__(self):
        return self.name


class TimeSeriesPredictTrainData(MaintainerInfo, TimeInfo):
    """时间序列预测训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        TimeSeriesPredictDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )

    train_data = models.FileField(
        verbose_name="训练数据",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的CSV训练数据文件",
        blank=True,
        null=True,
    )

    metadata = S3JSONField(
        bucket_name="munchkin-public",
        compressed=True,
        verbose_name="元数据",
        blank=True,
        null=True,
        help_text="存储在MinIO中的训练数据元信息文件路径",
    )

    is_train_data = models.BooleanField(
        default=False,
        verbose_name="是否为训练数据",
        help_text="是否为训练数据"
    )

    is_val_data = models.BooleanField(
        default=False,
        verbose_name="是否为验证数据",
        help_text="是否为验证数据"
    )

    is_test_data = models.BooleanField(
        default=False,
        verbose_name="是否为测试数据",
        help_text="是否为测试数据"
    )

    class Meta:
        verbose_name = "时间序列预测训练数据"
        verbose_name_plural = "时间序列预测训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"


class TimeSeriesPredictDatasetRelease(MaintainerInfo, TimeInfo):
    """时间序列预测数据集发布版本"""

    name = models.CharField(
        max_length=100,
        verbose_name="发布版本名称",
        help_text="数据集发布版本的名称"
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="版本描述",
        help_text="发布版本的详细描述"
    )

    dataset = models.ForeignKey(
        TimeSeriesPredictDataset,
        on_delete=models.CASCADE,
        related_name="releases",
        verbose_name="数据集",
        help_text="关联的数据集"
    )

    version = models.CharField(
        max_length=50,
        verbose_name="版本号",
        help_text="数据集版本号，如 v1.0.0"
    )

    dataset_file = models.FileField(
        verbose_name="数据集压缩包",
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        help_text="存储在MinIO中的数据集ZIP压缩包"
    )

    file_size = models.BigIntegerField(
        verbose_name="文件大小",
        help_text="压缩包文件大小（字节）",
        default=0
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "待发布"),
            ("published", "已发布"),
            ("failed", "发布失败"),
            ("archived", "归档")
        ],
        default="pending",
        verbose_name="发布状态",
        help_text="数据集发布状态"
    )

    metadata = models.JSONField(
        verbose_name="数据集元信息",
        default=dict,
        blank=True,
        help_text="数据集的统计信息和质量指标，不包含训练配置"
    )

    class Meta:
        verbose_name = "时间序列预测数据集发布版本"
        verbose_name_plural = "时间序列预测数据集发布版本"
        ordering = ["-created_at"]
        unique_together = [["dataset", "version"]]

    def __str__(self):
        return f"{self.dataset.name} - {self.version}"


class TimeSeriesPredictTrainJob(MaintainerInfo, TimeInfo):
    """时间序列预测训练任务"""

    name = models.CharField(max_length=100, verbose_name="任务名称")
    description = models.TextField(blank=True, null=True, verbose_name="任务描述")

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', '待训练'),
            ('running', '训练中'),
            ('completed', '已完成'),
            ('failed', '训练失败'),
        ],
        default='pending',
        verbose_name="任务状态",
        help_text="训练任务的当前状态"
    )

    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的时间序列预测算法模型",
        choices=[
            ('Prophet', 'Prophet'),
            ('GradientBoosting', 'GradientBoosting')
        ]
    )

    dataset_version = models.ForeignKey(
        'TimeSeriesPredictDatasetRelease',
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="数据集版本",
        help_text="关联的时间序列预测数据集版本"
    )

    # 数据库存储 - 工作数据，供API快速查询
    hyperopt_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="训练配置",
        help_text="存储在数据库中，供API快速返回"
    )

    # MinIO 存储 - 归档备份
    config_url = models.FileField(
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="配置文件备份",
        help_text="MinIO 中的 JSON 文件备份"
    )

    max_evals = models.IntegerField(
        default=200,
        verbose_name="最大评估次数",
        help_text="超参数优化的最大评估次数"
    )

    class Meta:
        verbose_name = "时间序列预测训练任务"
        verbose_name_plural = "时间序列预测训练任务"
    
    def save(self, *args, **kwargs):
        """保存时自动同步配置到 MinIO（先保存获得 pk，再同步文件）"""
        from apps.core.logger import opspilot_logger as logger
        
        # 如果仅更新指定字段且不包含配置相关字段，跳过文件同步
        update_fields = kwargs.get('update_fields')
        config_related_fields = {'hyperopt_config', 'config_url', 'algorithm', 'dataset_version'}
        
        if update_fields and not any(field in config_related_fields for field in update_fields):
            # 仅更新状态等非配置字段，直接保存
            super().save(*args, **kwargs)
            return
        
        # 1. 先保存到数据库，获得 pk
        super().save(*args, **kwargs)
        
        # 2. 基于真实 pk 同步文件到 MinIO
        config_updated = False
        
        if self.hyperopt_config:
            # 有配置内容 → 补全并上传到 MinIO
            self._sync_config_to_minio()
            config_updated = True
        elif self.config_url:
            # 配置为空 → 删除 MinIO 文件
            try:
                self.config_url.delete(save=False)
                logger.info(f"Deleted config file (empty config) for TrainJob {self.pk}")
                self.config_url = None
                config_updated = True
            except Exception as e:
                logger.warning(f"Failed to delete config file: {e}")
        
        # 3. 如果 config_url 有变化，更新数据库
        if config_updated:
            super().save(update_fields=['config_url'])
    
    def _sync_config_to_minio(self):
        """将 hyperopt_config 同步上传到 MinIO（自动补全 model 和 mlflow 配置）"""
        from django.core.files.base import ContentFile
        import json
        import uuid
        from apps.core.logger import opspilot_logger as logger
        
        # 删除旧文件
        if self.config_url:
            try:
                self.config_url.delete(save=False)
                logger.info(f"Deleted old config file for TrainJob {self.pk}")
            except Exception as e:
                logger.warning(f"Failed to delete old config file: {e}")
        
        # 补全配置文件
        try:
            complete_config = self._build_complete_config()
            
            # 上传新文件
            content = json.dumps(complete_config, ensure_ascii=False, indent=2)
            filename = f'config_{self.pk or "new"}_{uuid.uuid4().hex[:8]}.json'
            self.config_url.save(
                filename,
                ContentFile(content.encode('utf-8')),
                save=False  # 重要：避免递归调用 save()
            )
            logger.info(f"Synced config to MinIO for TrainJob {self.pk}: {filename}")
        except Exception as e:
            logger.error(f"Failed to sync config to MinIO: {e}", exc_info=True)
    
    def _build_complete_config(self):
        """构建完整的配置文件（补全 model 和 mlflow 部分）"""
        # 基础配置（来自前端）
        config = dict(self.hyperopt_config) if self.hyperopt_config else {}
        
        # 生成模型标识：algorithm_name_id（此时 pk 已存在）
        model_identifier = f"TimeseriesPredict_{self.algorithm}_{self.pk}"
        
        # 补充 model 配置
        config['model'] = {
            'type': self.algorithm,
            'name': model_identifier
        }
        
        # 补充 mlflow 配置
        config['mlflow'] = {
            'experiment_name': model_identifier
        }
        
        return config


class TimeSeriesPredictTrainHistory(MaintainerInfo, TimeInfo, DataPointFeaturesInfo):
    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的时间序列预测算法模型",
        choices=[
            ('Prophet', 'Prophet'),
            ('GradientBoosting', 'GradientBoosting')
        ]
    )

    dataset_version = models.ForeignKey(
        'TimeSeriesPredictDatasetRelease',
        on_delete=models.CASCADE,
        related_name="train_histories",
        verbose_name="数据集版本",
        help_text="关联的时间序列预测数据集版本"
    )

    # 数据库存储 - 工作数据，供API快速查询
    hyperopt_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="训练配置",
        help_text="存储在数据库中，供API快速返回"
    )

    # MinIO 存储 - 归档备份
    config_url = models.FileField(
        storage=MinioBackend(bucket_name="munchkin-public"),
        upload_to=iso_date_prefix,
        blank=True,
        null=True,
        verbose_name="配置文件备份",
        help_text="MinIO 中的 JSON 文件备份"
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('running', '训练中'),
            ('completed', '已完成'),
            ('failed', '训练失败'),
        ],
        default='pending',
        verbose_name="任务状态",
        help_text="训练任务的当前状态"
    )

    class Meta:
        verbose_name = "时间序列预测训练历史"
        verbose_name_plural = "时间序列预测训练历史"
    
    def save(self, *args, **kwargs):
        """保存时自动同步配置到 MinIO（先保存获得 pk，再同步文件）"""
        from apps.core.logger import opspilot_logger as logger
        
        # 1. 先保存到数据库，获得 pk
        super().save(*args, **kwargs)
        
        # 2. 基于真实 pk 同步文件到 MinIO
        config_updated = False
        
        if self.hyperopt_config:
            # 有配置内容 → 补全并上传到 MinIO
            self._sync_config_to_minio()
            config_updated = True
        elif self.config_url:
            # 配置为空 → 删除 MinIO 文件
            try:
                self.config_url.delete(save=False)
                logger.info(f"Deleted config file (empty config) for TrainHistory {self.pk}")
                self.config_url = None
                config_updated = True
            except Exception as e:
                logger.warning(f"Failed to delete config file: {e}")
        
        # 3. 如果 config_url 有变化，更新数据库
        if config_updated:
            super().save(update_fields=['config_url'])
    
    def _sync_config_to_minio(self):
        """将 hyperopt_config 同步上传到 MinIO（自动补全 model 和 mlflow 配置）"""
        from django.core.files.base import ContentFile
        import json
        import uuid
        from apps.core.logger import opspilot_logger as logger
        
        # 删除旧文件
        if self.config_url:
            try:
                self.config_url.delete(save=False)
                logger.info(f"Deleted old config file for TrainHistory {self.pk}")
            except Exception as e:
                logger.warning(f"Failed to delete old config file: {e}")
        
        # 补全配置文件
        try:
            complete_config = self._build_complete_config()
            
            # 上传新文件
            content = json.dumps(complete_config, ensure_ascii=False, indent=2)
            filename = f'config_{self.pk or "new"}_{uuid.uuid4().hex[:8]}.json'
            self.config_url.save(
                filename,
                ContentFile(content.encode('utf-8')),
                save=False  # 重要：避免递归调用 save()
            )
            logger.info(f"Synced config to MinIO for TrainHistory {self.pk}: {filename}")
        except Exception as e:
            logger.error(f"Failed to sync config to MinIO: {e}", exc_info=True)
    
    def _build_complete_config(self):
        """构建完整的配置文件（补全 model 和 mlflow 部分）"""
        # 基础配置（来自前端）
        config = dict(self.hyperopt_config) if self.hyperopt_config else {}
        
        # 生成模型标识：algorithm_history_id（此时 pk 已存在）
        model_identifier = f"{self.algorithm}_history_{self.pk}"
        
        # 补充 model 配置
        config['model'] = {
            'type': self.algorithm,
            'name': model_identifier
        }
        
        # 补充 mlflow 配置
        config['mlflow'] = {
            'experiment_name': model_identifier
        }
        
        return config


class TimeSeriesPredictServing(MaintainerInfo, TimeInfo):
    name = models.CharField(
        max_length=100,
        verbose_name="服务名称",
        help_text="服务的名称",
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="服务描述",
        help_text="服务的详细描述",
    )
    time_series_predict_train_job = models.ForeignKey(
        TimeSeriesPredictTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="模型ID",
        help_text="关联的时间序列预测训练任务模型ID",
    )
    model_version = models.CharField(
        max_length=50,
        default="latest",
        verbose_name="模型版本",
        help_text="模型版本",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("inactive", "Inactive")
        ],
        default="active",
        verbose_name="服务状态",
        help_text="服务的当前状态",
    )

    class Meta:
        verbose_name = "时间序列预测服务"
        verbose_name_plural = "时间序列预测服务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
