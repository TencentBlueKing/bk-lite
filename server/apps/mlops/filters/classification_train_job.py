from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter

from apps.mlops.models.classification_train_job import ClassificationTrainJob


class ClassificationTrainJobFilter(FilterSet):
    """分类任务训练作业过滤器"""
    
    name = CharFilter(field_name="name", lookup_expr="icontains", label="任务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=ClassificationTrainJob._meta.get_field('status').choices,
        label="任务状态"
    )
    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=ClassificationTrainJob._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    train_data_id__name = CharFilter(field_name="train_data_id__name", lookup_expr="icontains", label="训练数据名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = ClassificationTrainJob
        fields = ["name", "status", "algorithm", "train_data_id", "created_by"]