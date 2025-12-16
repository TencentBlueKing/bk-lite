from django_filters import FilterSet, CharFilter, DateTimeFilter, ChoiceFilter, BooleanFilter

from apps.mlops.models.classification import *


class ClassificationDatasetFilter(FilterSet):
    """分类任务数据集过滤器"""
    
    name = CharFilter(field_name="name", lookup_expr="icontains", label="数据集名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = ClassificationDataset
        fields = ["name", "created_by"]

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

class ClassificationTrainDataFilter(FilterSet):
    """分类任务训练数据过滤器"""
    
    name = CharFilter(field_name="name", lookup_expr="icontains", label="训练数据名称")
    dataset__name = CharFilter(field_name="dataset__name", lookup_expr="icontains", label="数据集名称")
    is_train_data = BooleanFilter(field_name="is_train_data", label="是否为训练数据")
    is_val_data = BooleanFilter(field_name="is_val_data", label="是否为验证数据")
    is_test_data = BooleanFilter(field_name="is_test_data", label="是否为测试数据")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = ClassificationTrainData
        fields = ["name", "dataset", "is_train_data", "is_val_data", "is_test_data", "created_by"]

class ClassificationTrainHistoryFilter(FilterSet):
    """分类任务训练历史记录过滤器"""
    
    algorithm = ChoiceFilter(
        field_name="algorithm",
        choices=ClassificationTrainHistory._meta.get_field('algorithm').choices,
        label="算法模型"
    )
    status = ChoiceFilter(
        field_name="status",
        choices=ClassificationTrainHistory._meta.get_field('status').choices,
        label="任务状态"
    )
    train_data_id__name = CharFilter(field_name="train_data_id__name", lookup_expr="icontains", label="训练数据名称")
    val_data_id__name = CharFilter(field_name="val_data_id__name", lookup_expr="icontains", label="验证数据名称")
    test_data_id__name = CharFilter(field_name="test_data_id__name", lookup_expr="icontains", label="测试数据名称")
    created_by = CharFilter(field_name="created_by", lookup_expr="icontains", label="创建者")
    created_at_start = DateTimeFilter(field_name="created_at", lookup_expr="gte", label="创建时间开始")
    created_at_end = DateTimeFilter(field_name="created_at", lookup_expr="lte", label="创建时间结束")

    class Meta:
        model = ClassificationTrainHistory
        fields = ["algorithm", "status", "train_data_id", "val_data_id", "test_data_id", "created_by"]

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