from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class RasaDatasets(MaintainerInfo, TimeInfo):
    "Rasa对话机器人数据集"

    name = models.CharField(max_length=100, verbose_name="数据集名称")
    description = models.TextField(blank=True, null=True, verbose_name="数据集描述")

    class Meta:
        verbose_name = "Rasa对话机器人数据集"
        verbose_name_plural = "Rasa对话机器人数据集"

    def __str__(self):
        return self.name


class RasaStory(MaintainerInfo, TimeInfo):
    """
    rasa故事训练数据
    """

    name = models.CharField(max_length=100, verbose_name="故事名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="stories",
        verbose_name="数据集"
    )

    steps = models.JSONField(
        verbose_name="故事步骤",
        default=list
    )

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaRule(MaintainerInfo, TimeInfo):

    name = models.CharField(max_length=100, verbose_name="规则名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name="数据集"
    )

    steps = models.JSONField(
        verbose_name="规则步骤",
        default=list
    )

    class Meta:
        verbose_name = "rasa规则"
        verbose_name_plural = "rasa规则"

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaIntent(MaintainerInfo, TimeInfo):

    name = models.CharField(max_length=100, verbose_name="意图名称", unique=True)
    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="intents",
        verbose_name="数据集"
    )

    example = models.JSONField(
        verbose_name="意图示例",
        default=list
    )

    class Meta:
        verbose_name = "意图"
        verbose_name_plural = "意图"

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaAction(MaintainerInfo, TimeInfo):
    "Rasa对话机器人Action"

    name = models.CharField(max_length=100, verbose_name="Action名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name="数据集"
    )

    class Meta:
        verbose_name = "Rasa对话机器人Action"
        verbose_name_plural = "Rasa对话机器人Actions"

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaSlot(MaintainerInfo, TimeInfo):
    """槽位模型"""
    name = models.CharField(max_length=100, verbose_name="槽位名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="slots",
        verbose_name="数据集"
    )

    SLOT_TYPE = [
        ('text', '记录普通文本'),
        ('categorical', '记录分类类别，枚举'),
        ('float', '记录数值'),
        ('bool', '记录布尔值'),
        ('list', '记录数值列表')
    ]

    slot_type = models.CharField(
        max_length=20,
        choices=SLOT_TYPE,
        verbose_name="槽位类型",
        default='text'
    )

    is_apply = models.BooleanField(
        default=False,
        verbose_name="是否应用"
    )

    values = models.JSONField(
        verbose_name="槽位值",
        default=list,
        help_text='type为category时选择填充此项'
    )

    class Meta:
        verbose_name = "槽位"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaResponse(MaintainerInfo, TimeInfo):

    name = models.CharField(max_length=100, verbose_name="响应名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name="数据集"
    )

    example = models.JSONField(
        verbose_name="响应示例",
        default=list
    )

    class Meta:
        verbose_name = "rasa响应"
        verbose_name_plural = "rasa响应"

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaForm(MaintainerInfo, TimeInfo):

    name = models.CharField(max_length=100, verbose_name="表单名称", unique=True)

    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="forms",
        verbose_name="数据集"
    )

    slots = models.JSONField(
        verbose_name="表单字段",
        default=list,
        help_text="表单字段列表"
    )

    class Meta:
        verbose_name = "表单"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaEntity(MaintainerInfo, TimeInfo):
    """
    Rasa 实体模型
    用于管理对话系统中的实体信息
    """

    ENTITY_TYPES = [
        ('Text', '自由标注'),
        ('Lookup', '枚举表'),
        # 可以根据需要添加更多类型
    ]

    name = models.CharField(max_length=100, verbose_name="实体名称", unique=True)
    dataset = models.ForeignKey(
        RasaDatasets,
        on_delete=models.CASCADE,
        related_name="entities",
        verbose_name="数据集"
    )

    entity_type = models.CharField(
        max_length=20,
        choices=ENTITY_TYPES,
        verbose_name="类型",
        default='Text'
    )

    # 存储实体值的列表
    example = models.JSONField(
        verbose_name="实体值",
        default=list,
        help_text="实体的具体取值列表"
    )

    # 可选：描述字段
    description = models.TextField(blank=True, null=True, verbose_name="描述")

    class Meta:
        verbose_name = "实体"
        verbose_name_plural = "实体"

    def __str__(self):
        return f'{self.name}-{self.dataset.name}'


class RasaPipeline(MaintainerInfo, TimeInfo):
    """Rasa训练管道模型"""

    name = models.CharField(max_length=100, verbose_name="管道名称", unique=True)
    description = models.TextField(blank=True, null=True, verbose_name="管道描述")

    # JSON配置字段，用于存储Rasa pipeline配置
    config = models.JSONField(
        verbose_name="管道配置",
        default=dict,
        help_text="Rasa pipeline配置，包含tokenizer、featurizer、classifier等组件"
    )

    # 关联多个数据集，一个pipeline可以关联多个dataset
    datasets = models.ManyToManyField(
        RasaDatasets,
        related_name="pipelines",
        verbose_name="关联数据集",
        blank=True,
        help_text="该管道关联的训练数据集"
    )

    class Meta:
        verbose_name = "Rasa训练管道"
        verbose_name_plural = "Rasa训练管道"

    def __str__(self):
        return self.name

    def get_dataset_count(self):
        """获取关联的数据集数量"""
        return self.datasets.count()

    def get_dataset_names(self):
        """获取关联的数据集名称列表"""
        return list(self.datasets.values_list('name', flat=True))
