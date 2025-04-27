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
