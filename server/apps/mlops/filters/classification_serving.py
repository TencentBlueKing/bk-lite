from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter

from apps.mlops.models.classification_serving import ClassificationServing


class ClassificationServingFilter(FilterSet):
    """分类任务服务过滤器"""
    
    name = CharFilter(field_name="name", lookup_expr="icontains", label="服务名称")
    status = ChoiceFilter(
        field_name="status",
        choices=ClassificationServing._meta.get_field('status').choices,
        label="服务状态"
    )
    model_version = CharFilter(field_name="model_version", lookup_expr="icontains", label="模型版本")
    classification_train_job__name = CharFilter(
        field_name="classification_train_job__name", 
        lookup_expr="icontains", 
        label="训练任务名称"
    )
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = ClassificationServing
        fields = ["name", "status", "model_version", "classification_train_job", "created_by"]