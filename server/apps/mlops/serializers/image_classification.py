from types import SimpleNamespace

from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.image_classification import *
from rest_framework import serializers
from apps.core.logger import mlops_logger as logger
from apps.mlops.utils.group_scope import (
    assert_dataset_version_scope,
    assert_parent_team_matches,
    assert_team_ownership,
    get_current_team,
    validate_requested_teams,
)


class ImageClassificationDatasetSerializer(AuthSerializer):
    """图片分类数据集序列化器"""

    permission_key = "dataset.image_classification_dataset"

    class Meta:
        model = ImageClassificationDataset
        fields = "__all__"

    def validate_team(self, value):
        return validate_requested_teams(self.context["request"], value)


class ImageClassificationTrainDataSerializer(AuthSerializer):
    """图片分类训练数据序列化器"""

    permission_key = "dataset.image_classification_train_data"

    class Meta:
        model = ImageClassificationTrainData
        fields = "__all__"
        extra_kwargs = {
            "train_data": {"required": False},
            "metadata": {"required": False},
        }

    def __init__(self, *args, **kwargs):
        """初始化序列化器，从请求上下文中获取参数"""
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.include_train_data = request.query_params.get("include_train_data", "false").lower() == "true"
            self.include_metadata = request.query_params.get("include_metadata", "false").lower() == "true"
        else:
            self.include_train_data = False
            self.include_metadata = False

    def to_representation(self, instance):
        """自定义返回数据，根据参数动态控制字段"""
        representation = super().to_representation(instance)

        # 根据查询参数控制大文件字段返回
        if not self.include_train_data:
            representation.pop("train_data", None)
        if not self.include_metadata:
            representation.pop("metadata", None)

        return representation

    def validate_dataset(self, value):
        request = self.context["request"]
        assert_team_ownership(value, get_current_team(request), "dataset", request=request)
        return value


class ImageClassificationDatasetReleaseSerializer(AuthSerializer):
    """图片分类数据集发布版本序列化器"""

    permission_key = "dataset.image_classification_dataset_release"

    dataset_name = serializers.CharField(source="dataset.name", read_only=True)

    # 添加只写字段用于接收文件ID
    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ImageClassificationDatasetRelease
        fields = "__all__"
        validators = []
        extra_kwargs = {
            "name": {"required": False},  # 创建时可选，会自动生成
            "dataset_file": {"required": False},  # 创建时不需要直接提供文件
            "file_size": {"required": False},
            "status": {"required": False},
        }

    def validate_version(self, value):
        """验证版本号格式"""
        import re

        if not re.match(r"^v\d+\.\d+\.\d+$", value):
            raise serializers.ValidationError("版本号格式应为 vX.Y.Z，例如：v1.0.0")
        return value

    def validate_dataset(self, value):
        request = self.context["request"]
        assert_team_ownership(value, get_current_team(request), "dataset", request=request)
        return value

    def create(self, validated_data):
        """
        自定义创建方法，支持从文件ID创建数据集发布版本
        """
        # 提取文件ID
        train_file_id = validated_data.pop("train_file_id", None)
        val_file_id = validated_data.pop("val_file_id", None)
        test_file_id = validated_data.pop("test_file_id", None)
        dataset = validated_data.get("dataset")
        version = validated_data.get("version")

        # 如果提供了文件ID，则执行文件打包逻辑
        if train_file_id and val_file_id and test_file_id:
            return self._create_from_files(validated_data, train_file_id, val_file_id, test_file_id)
        else:
            existing = ImageClassificationDatasetRelease._default_manager.filter(dataset=dataset, version=version).first()
            if existing and existing.status == "failed":
                existing.dataset_file = validated_data.get("dataset_file")
                existing.status = "pending"
                existing.file_size = 0
                existing.metadata = {}
                existing.save(update_fields=["dataset_file", "status", "file_size", "metadata"])
                return existing

            # 否则使用标准创建（适用于直接上传ZIP文件的场景）
            return super().create(validated_data)

    def _create_from_files(self, validated_data, train_file_id, val_file_id, test_file_id):
        """
        从训练数据文件ID创建数据集发布版本（异步）

        创建 pending 状态的记录，触发 Celery 任务进行异步处理
        """
        dataset = validated_data.get("dataset")
        version = validated_data.get("version")
        name = validated_data.get("name")
        description = validated_data.get("description", "")

        try:
            # 验证文件是否存在
            train_obj = ImageClassificationTrainData.objects.get(id=train_file_id, dataset=dataset)
            val_obj = ImageClassificationTrainData.objects.get(id=val_file_id, dataset=dataset)
            test_obj = ImageClassificationTrainData.objects.get(id=test_file_id, dataset=dataset)

            # 检查是否已有相同版本的记录（失败记录允许重试）
            existing = ImageClassificationDatasetRelease.objects.filter(dataset=dataset, version=version).first()

            if existing:
                if existing.status == "failed":
                    release = existing
                    release.status = "pending"
                    release.file_size = 0
                    release.metadata = {}
                    release.save(update_fields=["status", "file_size", "metadata"])
                else:
                    logger.info(f"数据集版本已存在 - Dataset: {dataset.id}, Version: {version}, Status: {existing.status}")
                    raise serializers.ValidationError(f"数据集 {dataset.name} 的版本 {version} 已存在或正在处理中")
            else:
                # 创建 pending 状态的发布记录
                validated_data["status"] = "pending"
                validated_data["file_size"] = 0
                validated_data["metadata"] = {}

                if not name:
                    validated_data["name"] = f"{dataset.name}_{version}"

                if not description:
                    validated_data["description"] = f"从数据集文件自动发布: {train_obj.name}, {val_obj.name}, {test_obj.name}"

                release = ImageClassificationDatasetRelease.objects.create(**validated_data)

            # 触发异步任务
            from apps.mlops.tasks.image_classification import (
                publish_dataset_release_async,
            )

            try:
                publish_dataset_release_async.delay(release.id, train_file_id, val_file_id, test_file_id)
            except Exception as task_error:
                logger.error(
                    f"投递 Celery 任务失败 - Release ID: {release.id}, Error: {str(task_error)}",
                    exc_info=True,
                )
                release.status = "failed"
                release.save(update_fields=["status"])
                raise serializers.ValidationError("投递异步任务失败")

            logger.info(f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}")

            return release

        except ImageClassificationTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError("创建发布任务失败")

    def validate(self, attrs):
        """验证数据集和版本的唯一性"""
        dataset = attrs.get("dataset")
        version = attrs.get("version")

        # 提取文件ID（如果存在）
        train_file_id = attrs.get("train_file_id")
        val_file_id = attrs.get("val_file_id")
        test_file_id = attrs.get("test_file_id")

        # 如果未提供文件ID，dataset_file 必须提供（直接上传模式）
        if not (train_file_id and val_file_id and test_file_id):
            if not attrs.get("dataset_file"):
                raise serializers.ValidationError({"dataset_file": "必须提供数据集文件或训练数据文件ID"})

        if dataset and version:
            existing_releases = ImageClassificationDatasetRelease._default_manager.filter(dataset=dataset, version=version)
            if self.instance:
                existing_releases = existing_releases.exclude(pk=self.instance.pk)

            existing = existing_releases.first()
            has_file_ids = bool(train_file_id and val_file_id and test_file_id)
            has_dataset_file = bool(attrs.get("dataset_file"))
            allow_failed_retry = bool(existing and existing.status == "failed" and (has_file_ids or has_dataset_file))

            if existing and not allow_failed_retry:
                raise serializers.ValidationError({"version": f"数据集 {dataset.name} 的版本 {version} 已存在"})

        return attrs


class ImageClassificationTrainJobSerializer(AuthSerializer):
    """图片分类训练任务序列化器"""

    permission_key = "train_job.image_classification_train_job"

    dataset_version_name = serializers.CharField(source="dataset_version.name", read_only=True)
    config_url_display = serializers.SerializerMethodField()

    class Meta:
        model = ImageClassificationTrainJob
        fields = "__all__"
        extra_kwargs = {
            "status": {"read_only": True},
            "config_url": {"read_only": True},
        }

    def get_config_url_display(self, obj):
        """获取配置文件的可访问URL"""
        if obj.config_url:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.config_url.url)
        return None

    def validate_hyperopt_config(self, value):
        """验证训练配置格式"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("hyperopt_config 必须是字典格式")

        # 验证必须包含 hyperparams 部分
        if "hyperparams" not in value:
            raise serializers.ValidationError("hyperopt_config 必须包含 hyperparams 字段")

        hyperparams = value["hyperparams"]
        if not isinstance(hyperparams, dict):
            raise serializers.ValidationError("hyperparams 必须是字典格式")

        return value

    def create(self, validated_data):
        """创建训练任务，自动设置为 pending 状态"""
        validated_data["status"] = "pending"
        return super().create(validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context["request"]
        dataset_version = attrs.get("dataset_version", getattr(self.instance, "dataset_version", None))
        team = attrs.get("team", getattr(self.instance, "team", None))
        assert_dataset_version_scope(dataset_version, team, request)
        return attrs

    def validate_team(self, value):
        return validate_requested_teams(self.context["request"], value)


class ImageClassificationServingSerializer(AuthSerializer):
    """图片分类服务序列化器"""

    permission_key = "serving.image_classification_serving"

    train_job_name = serializers.CharField(source="train_job.name", read_only=True)
    train_job_algorithm = serializers.CharField(source="train_job.algorithm", read_only=True)
    actual_port = serializers.SerializerMethodField()
    container_status = serializers.SerializerMethodField()

    class Meta:
        model = ImageClassificationServing
        fields = "__all__"
        extra_kwargs = {"container_info": {"read_only": True}}

    def validate_train_job(self, value):
        request = self.context["request"]
        assert_team_ownership(value, get_current_team(request), "train_job", request=request)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        train_job = attrs.get("train_job", getattr(self.instance, "train_job", None))
        team = attrs.get("team", getattr(self.instance, "team", None))
        if train_job is not None and team is not None:
            field_name = "train_job" if "train_job" in attrs or "team" not in attrs else "team"
            assert_parent_team_matches(SimpleNamespace(team=team), train_job, field_name)

        return attrs

    def get_actual_port(self, obj):
        """从 container_info 中获取实际端口"""
        if obj.container_info and "port" in obj.container_info:
            return obj.container_info["port"]
        return obj.port

    def get_container_status(self, obj):
        """从 container_info 中获取容器状态"""
        if obj.container_info and "status" in obj.container_info:
            return obj.container_info["status"]
        return "unknown"

    def validate_model_version(self, value):
        """验证模型版本格式"""
        if value != "latest" and not value.isdigit():
            raise serializers.ValidationError("模型版本必须是 'latest' 或正整数（如：1, 2, 3）")
        return value

    def validate_team(self, value):
        return validate_requested_teams(self.context["request"], value)
