from django.db import models
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class ClassificationTrainJob(MaintainerInfo, TimeInfo):
    """分类任务训练作业"""

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
        help_text="使用的分类算法模型",
        choices=[
            ('RandomForest', 'Random Forest'),
            ('XGBoost', 'XGBoost'),
            ('LogisticRegression', 'Logistic Regression'),
            ('SVM', 'Support Vector Machine'),
            ('NeuralNetwork', 'Neural Network'),
        ]
    )

    train_data_id = models.ForeignKey(
        'ClassificationTrainData',
        on_delete=models.CASCADE,
        related_name="train_jobs",
        verbose_name="训练数据集",
        help_text="关联的分类训练数据集"
    )

    val_data_id = models.ForeignKey(
        'ClassificationTrainData',
        on_delete=models.CASCADE,
        related_name="val_jobs",
        verbose_name="验证数据集",
        help_text="关联的分类验证数据集"
    )

    test_data_id = models.ForeignKey(
        'ClassificationTrainData',
        on_delete=models.CASCADE,
        related_name="test_jobs",
        verbose_name="测试数据集",
        help_text="关联的分类测试数据集"
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
    
    
    class Meta:
        verbose_name = "分类任务训练作业"
        verbose_name_plural = "分类任务训练作业"
        
    def __str__(self):
        return self.name