from config.drf.viewsets import ModelViewSet
from apps.mlops.models.rasa import *
from apps.mlops.serializers.rasa import *
from apps.mlops.filters.rasa import *
from config.drf.pagination import CustomPageNumberPagination
from apps.core.decorators.api_permission import HasPermission
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Count, Q


class RasaDatasetViewSet(ModelViewSet):
    filterset_class = RasaDatasetFilter
    ordering = ("-id",)
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.rasa_dataset"
    queryset = RasaDatasets.objects.all()
    serializer_class = RasaDatasetSerializer


class RasaActionViewSet(ModelViewSet):
    queryset = RasaAction.objects.all()
    serializer_class = RasaActionSerializer
    filterset_class = RasaActionFilter
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_action'
    ordering = ('-id',)


class RasaStoryViewSet(ModelViewSet):
    filterset_class = RasaStoryFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.rasa_story"
    queryset = RasaStory.objects.all()
    serializer_class = RasaStorySerializer
    ordering = ("-id",)


class RasaSlotViewSet(ModelViewSet):
    filterset_class = RasaSlotFilter
    ordering = ('-id',)
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_slot'
    queryset = RasaSlot.objects.all()
    serializer_class = RasaSlotSerializer


class RasaRuleViewSet(ModelViewSet):
    filterset_class = RasaRuleFilter
    ordering = ('-id',)
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_rule'
    queryset = RasaRule.objects.all()
    serializer_class = RasaRuleSerializer


class RasaResponseViewSet(ModelViewSet):
    filterset_class = RasaResponseFilter
    ordering = ('-id',)
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_response'
    queryset = RasaResponse.objects.all()
    serializer_class = RasaResponseSerializer


class RasaIntentViewSet(ModelViewSet):
    queryset = RasaIntent.objects.all()
    serializer_class = RasaIntentSerializer
    filterset_class = RasaIntentFilter
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_intent'
    ordering = ('-id',)


class RasaFormViewSet(ModelViewSet):
    filterset_class = RasaFormFilter
    ordering = ('-id',)
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_form'
    queryset = RasaForm.objects.all()
    serializer_class = RasaFormSerializer


class RasaEntityViewSet(ModelViewSet):
    filterset_class = RasaEntityFilter
    ordering = ('-id',)
    pagination_class = CustomPageNumberPagination
    permission_key = 'dataset.rasa_entity'
    queryset = RasaEntity.objects.all()
    serializer_class = RasaEntitySerializer


class RasaPipelineViewSet(ModelViewSet):
    """Rasa训练管道视图集"""

    queryset = RasaPipeline.objects.all()
    serializer_class = RasaPipelineSerializer
    filterset_class = RasaPipelineFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "dataset.rasa_pipeline"
    ordering = ("-id",)

    def get_queryset(self):
        """
        优化查询，预加载关联的数据集
        """
        return super().get_queryset().prefetch_related('datasets')

    @HasPermission("dataset.rasa_pipeline-View")
    def list(self, request, *args, **kwargs):
        """列表查询"""
        return super().list(request, *args, **kwargs)

    @HasPermission("dataset.rasa_pipeline-Add")
    def create(self, request, *args, **kwargs):
        """创建新管道"""
        return super().create(request, *args, **kwargs)

    @HasPermission("dataset.rasa_pipeline-View")
    def retrieve(self, request, *args, **kwargs):
        """获取单个管道详情"""
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("dataset.rasa_pipeline-Edit")
    def update(self, request, *args, **kwargs):
        """更新管道"""
        return super().update(request, *args, **kwargs)

    @HasPermission("dataset.rasa_pipeline-Delete")
    def destroy(self, request, *args, **kwargs):
        """删除管道"""
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='simple')
    @HasPermission("dataset.rasa_pipeline-View")
    def simple_list(self, request):
        """
        获取简化的管道列表，用于下拉选择等场景
        """
        queryset = self.filter_queryset(self.get_queryset())
        serializer = RasaPipelineSimpleSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='add_datasets')
    @HasPermission("dataset.rasa_pipeline-Edit")
    def add_datasets(self, request, pk=None):
        """
        为管道添加数据集
        请求体格式: {"dataset_ids": [1, 2, 3]}
        """
        try:
            pipeline = self.get_object()
            dataset_ids = request.data.get('dataset_ids', [])

            if not dataset_ids:
                return Response(
                    {'error': '请提供要添加的数据集ID列表'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 验证数据集是否存在
            existing_datasets = RasaDatasets.objects.filter(id__in=dataset_ids)
            if len(existing_datasets) != len(dataset_ids):
                return Response(
                    {'error': '部分数据集不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 添加数据集关联
            with transaction.atomic():
                pipeline.datasets.add(*existing_datasets)

            return Response({
                'message': f'成功添加 {len(existing_datasets)} 个数据集',
                'added_datasets': [{'id': ds.id, 'name': ds.name} for ds in existing_datasets]
            })

        except Exception as e:
            return Response(
                {'error': f'添加数据集失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='remove_datasets')
    @HasPermission("dataset.rasa_pipeline-Edit")
    def remove_datasets(self, request, pk=None):
        """
        从管道中移除数据集
        请求体格式: {"dataset_ids": [1, 2, 3]}
        """
        try:
            pipeline = self.get_object()
            dataset_ids = request.data.get('dataset_ids', [])

            if not dataset_ids:
                return Response(
                    {'error': '请提供要移除的数据集ID列表'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 验证要移除的数据集是否已关联
            current_datasets = pipeline.datasets.filter(id__in=dataset_ids)

            # 移除数据集关联
            with transaction.atomic():
                pipeline.datasets.remove(*current_datasets)

            return Response({
                'message': f'成功移除 {len(current_datasets)} 个数据集',
                'removed_datasets': [{'id': ds.id, 'name': ds.name} for ds in current_datasets]
            })

        except Exception as e:
            return Response(
                {'error': f'移除数据集失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='set_datasets')
    @HasPermission("dataset.rasa_pipeline-Edit")
    def set_datasets(self, request, pk=None):
        """
        设置管道的数据集（替换现有关联）
        请求体格式: {"dataset_ids": [1, 2, 3]}
        """
        try:
            pipeline = self.get_object()
            dataset_ids = request.data.get('dataset_ids', [])

            # 验证数据集是否存在
            if dataset_ids:
                existing_datasets = RasaDatasets.objects.filter(id__in=dataset_ids)
                if len(existing_datasets) != len(dataset_ids):
                    return Response(
                        {'error': '部分数据集不存在'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                existing_datasets = []

            # 设置数据集关联
            with transaction.atomic():
                pipeline.datasets.set(existing_datasets)

            return Response({
                'message': f'成功设置 {len(existing_datasets)} 个数据集',
                'current_datasets': [{'id': ds.id, 'name': ds.name} for ds in existing_datasets]
            })

        except Exception as e:
            return Response(
                {'error': f'设置数据集失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'], url_path='datasets')
    @HasPermission("dataset.rasa_pipeline-View")
    def get_datasets(self, request, pk=None):
        """
        获取管道关联的所有数据集
        """
        try:
            pipeline = self.get_object()
            datasets = pipeline.datasets.all()

            datasets_data = []
            for dataset in datasets:
                datasets_data.append({
                    'id': dataset.id,
                    'name': dataset.name,
                    'description': dataset.description,
                    'created_at': dataset.created_at.strftime('%Y-%m-%d %H:%M:%S') if dataset.created_at else None,
                    'created_by': dataset.created_by,
                })

            return Response({
                'pipeline_id': pipeline.id,
                'pipeline_name': pipeline.name,
                'datasets': datasets_data,
                'total_count': len(datasets_data)
            })

        except Exception as e:
            return Response(
                {'error': f'获取数据集失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='validate_config')
    @HasPermission("dataset.rasa_pipeline-View")
    def validate_config(self, request, pk=None):
        """
        验证管道配置
        请求体格式: {"config": {...}} 或使用当前管道的配置
        """
        try:
            pipeline = self.get_object()
            config = request.data.get('config', pipeline.config)

            # 基本格式验证
            if not isinstance(config, dict):
                return Response(
                    {'valid': False, 'error': '配置必须是有效的JSON对象'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 检查必要字段
            errors = []
            if 'pipeline' not in config:
                errors.append('配置中缺少 pipeline 字段')

            # 可以添加更多验证逻辑
            if config.get('pipeline'):
                if not isinstance(config['pipeline'], list):
                    errors.append('pipeline 字段必须是数组')

            if errors:
                return Response({
                    'valid': False,
                    'errors': errors
                })

            return Response({
                'valid': True,
                'message': '配置验证通过'
            })

        except Exception as e:
            return Response(
                {'error': f'配置验证失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='statistics')
    @HasPermission("dataset.rasa_pipeline-View")
    def statistics(self, request):
        """
        获取管道统计信息
        """
        try:
            queryset = self.get_queryset()

            # 基本统计
            total_count = queryset.count()

            # 按数据集数量分组统计
            dataset_count_stats = queryset.annotate(
                dataset_count=Count('datasets')
            ).values('dataset_count').annotate(
                pipeline_count=Count('id')
            ).order_by('dataset_count')

            # 有配置的管道数量
            configured_count = queryset.exclude(Q(config__isnull=True) | Q(config={})).count()

            # 最近创建的管道
            recent_pipelines = queryset.order_by('-created_at')[:5].values(
                'id', 'name', 'created_at', 'created_by'
            )

            return Response({
                'total_pipelines': total_count,
                'configured_pipelines': configured_count,
                'unconfigured_pipelines': total_count - configured_count,
                'dataset_distribution': list(dataset_count_stats),
                'recent_pipelines': list(recent_pipelines)
            })

        except Exception as e:
            return Response(
                {'error': f'获取统计信息失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='clone')
    @HasPermission("dataset.rasa_pipeline-Add")
    def clone_pipeline(self, request, pk=None):
        """
        克隆管道
        请求体格式: {"name": "new_pipeline_name", "description": "description"}
        """
        try:
            original_pipeline = self.get_object()
            new_name = request.data.get('name')
            new_description = request.data.get('description', f'从 {original_pipeline.name} 克隆')

            if not new_name:
                return Response(
                    {'error': '请提供新管道的名称'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 检查名称是否已存在
            if RasaPipeline.objects.filter(name=new_name).exists():
                return Response(
                    {'error': '管道名称已存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():
                # 创建新管道
                new_pipeline = RasaPipeline.objects.create(
                    name=new_name,
                    description=new_description,
                    config=original_pipeline.config.copy() if original_pipeline.config else {},
                    created_by=request.user.username if hasattr(request.user, 'username') else 'admin',
                    updated_by=request.user.username if hasattr(request.user, 'username') else 'admin'
                )

                # 复制数据集关联
                if original_pipeline.datasets.exists():
                    new_pipeline.datasets.set(original_pipeline.datasets.all())

            serializer = self.get_serializer(new_pipeline)
            return Response({
                'message': '管道克隆成功',
                'pipeline': serializer.data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {'error': f'克隆管道失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
