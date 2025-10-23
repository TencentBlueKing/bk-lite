from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.mlops.models.data_points_features_info import DataPointFeaturesInfo


class LogClusteringDataset(MaintainerInfo, TimeInfo):
    """日志聚类数据集"""

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "日志聚类数据集"
        verbose_name_plural = "日志聚类数据集"

    def __str__(self):
        return self.name


class LogClusteringTrainData(MaintainerInfo, TimeInfo):
    """日志聚类训练数据模型"""

    name = models.CharField(max_length=100, verbose_name="训练数据名称")

    dataset = models.ForeignKey(
        LogClusteringDataset,
        on_delete=models.CASCADE,
        related_name="train_data",
        verbose_name="数据集",
    )

    train_data = models.JSONField(
        verbose_name="训练数据",
        help_text="存储日志聚类训练数据",
    )

    metadata = models.JSONField(
        verbose_name="元数据",
        blank=True,
        null=True,
        help_text="训练数据元信息",
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

    # 日志聚类特有字段
    log_count = models.IntegerField(
        default=0,
        verbose_name="日志条数",
        help_text="数据集中包含的日志条数"
    )

    log_source = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="日志来源",
        help_text="日志数据的来源系统或文件"
    )

    class Meta:
        verbose_name = "日志聚类训练数据"
        verbose_name_plural = "日志聚类训练数据"

    def __str__(self):
        return f"{self.name} - {self.dataset.name}"


class LogClusteringTrainJob(MaintainerInfo, TimeInfo):
    """日志聚类训练任务"""

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
        help_text="使用的日志聚类算法模型",
        choices=[
            ('KMeans', 'K-Means'),
            ('DBSCAN', 'DBSCAN'),
            ('AgglomerativeClustering', '层次聚类'),
            ('Drain', 'Drain'),
            ('LogCluster', 'LogCluster'),
        ]
    )

    train_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="训练数据集",
        help_text="关联的日志聚类训练数据集"
    )

    val_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="val_jobs",
        verbose_name="验证数据集",
        help_text="关联的日志聚类验证数据集",
        blank=True,
        null=True
    )

    test_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="test_jobs",
        verbose_name="测试数据集",
        help_text="关联的日志聚类测试数据集",
        blank=True,
        null=True
    )

    hyperopt_config = models.JSONField(
        verbose_name="超参数优化配置",
        help_text="用于超参数优化的配置参数",
        default=dict,
    )

    max_evals = models.IntegerField(
        default=200,
        verbose_name="最大评估次数",
        help_text="超参数优化的最大评估次数"
    )

    # 日志聚类特有参数
    cluster_count = models.IntegerField(
        default=10,
        verbose_name="聚类数量",
        help_text="预期的聚类簇数量（适用于K-Means等算法）"
    )

    min_samples = models.IntegerField(
        default=5,
        verbose_name="最小样本数",
        help_text="形成聚类所需的最小样本数（适用于DBSCAN等算法）"
    )

    eps = models.FloatField(
        default=0.5,
        verbose_name="邻域半径",
        help_text="DBSCAN算法的邻域半径参数"
    )

    class Meta:
        verbose_name = "日志聚类训练任务"
        verbose_name_plural = "日志聚类训练任务"

    def __str__(self):
        return self.name


class LogClusteringTrainHistory(MaintainerInfo, TimeInfo, DataPointFeaturesInfo):
    algorithm = models.CharField(
        max_length=50,
        verbose_name="算法模型",
        help_text="使用的日志聚类算法模型",
        choices=[
            ('KMeans', 'K-Means'),
            ('DBSCAN', 'DBSCAN'),
            ('AgglomerativeClustering', '层次聚类'),
            ('Drain', 'Drain'),
            ('LogCluster', 'LogCluster'),
        ]
    )

    train_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="train_history",
        verbose_name="训练数据集",
        help_text="关联的日志聚类训练数据集"
    )

    val_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="val_history",
        verbose_name="验证数据集",
        help_text="关联的日志聚类验证数据集",
        blank=True,
        null=True
    )

    test_data_id = models.ForeignKey(
        'LogClusteringTrainData',
        on_delete=models.CASCADE,
        related_name="test_history",
        verbose_name="测试数据集",
        help_text="关联的日志聚类测试数据集",
        blank=True,
        null=True
    )

    hyperopt_config = models.JSONField(
        verbose_name="超参数优化配置",
        help_text="用于超参数优化的配置参数",
        default=dict,
    )

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

    # 日志聚类特有训练结果字段
    cluster_count = models.IntegerField(
        default=0,
        verbose_name="实际聚类数量",
        help_text="训练后实际产生的聚类簇数量"
    )

    silhouette_score = models.FloatField(
        blank=True,
        null=True,
        verbose_name="轮廓系数",
        help_text="聚类质量评估的轮廓系数"
    )

    davies_bouldin_score = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Davies-Bouldin指数",
        help_text="聚类质量评估的Davies-Bouldin指数"
    )

    calinski_harabasz_score = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Calinski-Harabasz指数",
        help_text="聚类质量评估的Calinski-Harabasz指数"
    )

    class Meta:
        verbose_name = "日志聚类训练历史"
        verbose_name_plural = "日志聚类训练历史"

    def __str__(self):
        return f"{self.algorithm} - {self.status}"


class LogClusteringServing(MaintainerInfo, TimeInfo):
    name = models.CharField(
        max_length=100,
        verbose_name="服务名称",
        help_text="日志聚类服务的名称",
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="服务描述",
        help_text="日志聚类服务的详细描述",
    )
    log_clustering_train_job = models.ForeignKey(
        LogClusteringTrainJob,
        on_delete=models.CASCADE,
        related_name="servings",
        verbose_name="模型ID",
        help_text="关联的日志聚类训练任务模型ID",
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

    # 日志聚类服务特有字段
    api_endpoint = models.URLField(
        blank=True,
        null=True,
        verbose_name="API端点",
        help_text="日志聚类服务的API访问端点"
    )

    max_requests_per_minute = models.IntegerField(
        default=1000,
        verbose_name="每分钟最大请求数",
        help_text="服务的请求频率限制"
    )

    supported_log_formats = models.JSONField(
        default=list,
        verbose_name="支持的日志格式",
        help_text="服务支持的日志格式列表"
    )

    class Meta:
        verbose_name = "日志聚类服务"
        verbose_name_plural = "日志聚类服务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}"
