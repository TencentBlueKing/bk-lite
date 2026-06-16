from django.db import models
from django.db.models import JSONField

CREATE_INST = "create_entity"
DELETE_INST = "delete_entity"
UPDATE_INST = "update_entity"

CREATE_INST_ASST = "create_edge"
DELETE_INST_ASST = "delete_edge"
EXECUTE = "execute"

OPERATE_TYPE_CHOICES = [
    (CREATE_INST, "创建"),
    (DELETE_INST, "删除"),
    (UPDATE_INST, "修改"),
    (EXECUTE, "执行"),
    (CREATE_INST_ASST, "创建关联"),
    (DELETE_INST_ASST, "取消关联"),
]

# 变更场景
DEVICE_LIFECYCLE = "device_lifecycle"
RELATION_CHANGE = "relation_change"
ORDINARY_ATTRIBUTE_CHANGE = "ordinary_attribute_change"
COLLECT_AUTOMATION_CHANGE = "collect_automation_change"
MODEL_MANAGEMENT_CHANGE = "model_management_change"
CUSTOM_REPORTING_CHANGE = "custom_reporting_change"

SCENARIO_CHOICES = [
    (DEVICE_LIFECYCLE, "设备流转"),
    (RELATION_CHANGE, "关系变更"),
    (ORDINARY_ATTRIBUTE_CHANGE, "普通属性变更"),
    (COLLECT_AUTOMATION_CHANGE, "自动采集"),
    (MODEL_MANAGEMENT_CHANGE, "模型管理变更"),
    (CUSTOM_REPORTING_CHANGE, "自定义上报变更"),
]

# 用户在"通用实例属性编辑页"可以修正的场景集合
INSTANCE_EDIT_CORRECTABLE_SCENARIOS = {ORDINARY_ATTRIBUTE_CHANGE, DEVICE_LIFECYCLE}

# 实例历史默认视图的高信号场景
INSTANCE_HISTORY_DEFAULT_SCENARIOS = [DEVICE_LIFECYCLE, RELATION_CHANGE, ORDINARY_ATTRIBUTE_CHANGE]


class ChangeRecord(models.Model):
    inst_id = models.BigIntegerField(db_index=True, verbose_name="实例ID")
    model_id = models.CharField(max_length=100, verbose_name="模型ID")
    label = models.CharField(max_length=50, verbose_name="标签ID")
    type = models.CharField(
        max_length=30, choices=OPERATE_TYPE_CHOICES, verbose_name="变更类型"
    )
    before_data = JSONField(default=dict, verbose_name="变更前实例信息")
    after_data = JSONField(default=dict, verbose_name="变更后实例信息")
    operator = models.CharField(max_length=50, default="", verbose_name="创建者")
    created_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name="创建时间"
    )
    model_object = models.CharField(max_length=50, default="", verbose_name="模型对象", help_text="模型对象")
    message = models.TextField(default="", verbose_name="操作信息", help_text="操作信息")
    scenario = models.CharField(
        max_length=40,
        default=ORDINARY_ATTRIBUTE_CHANGE,
        choices=SCENARIO_CHOICES,
        db_index=True,
        verbose_name="变更场景",
    )
