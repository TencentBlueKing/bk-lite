from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.classification import *
from rest_framework import serializers


class ClassificationDatasetSerializer(AuthSerializer):
    """分类任务数据集序列化器"""

    permission_key = "dataset.classification_dataset"

    class Meta:
        model = ClassificationDataset
        fields = "__all__"


class ClassificationServingSerializer(AuthSerializer):
    """分类任务服务序列化器"""

    permission_key = "dataset.classification_serving"

    class Meta:
        model = ClassificationServing
        fields = "__all__"


class ClassificationTrainDataSerializer(AuthSerializer):
    """分类任务训练数据序列化器"""

    permission_key = "dataset.classification_train_data"

    class Meta:
        model = ClassificationTrainData
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": False},
            "train_data": {"required": False},
            "dataset": {"required": False},
        }

    def __init__(self, *args, **kwargs):
        """
        初始化序列化器，从请求上下文中获取 include_train_data 参数
        """
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            self.include_train_data = (
                request.query_params.get("include_train_data", "false").lower()
                == "true"
            )
            self.include_metadata = (
                request.query_params.get("include_metadata", "false").lower() == "true"
            )
        else:
            self.include_train_data = False
            self.include_metadata = False

    def validate_train_data(self, value):
        """校验CSV格式"""
        import pandas as pd

        try:
            df = pd.read_csv(value)

            # 检查必需列
            required_columns = ["text", "label"]
            missing = set(required_columns) - set(df.columns)
            if missing:
                raise serializers.ValidationError(f"缺少必需列: {', '.join(missing)}")

            # 检查数据类型
            if df["text"].isnull().any():
                raise serializers.ValidationError("'text'列包含空值")

            if df["label"].isnull().any():
                raise serializers.ValidationError("'label'列包含空值")

            return value
        except pd.errors.ParserError as e:
            raise serializers.ValidationError(f"无效的CSV格式: {str(e)}")

    def to_representation(self, instance):
        """
        自定义返回数据，根据 include_train_data 参数动态控制 train_data 字段
        当 include_train_data=true 时，后端直接读取 CSV 并解析为结构化数据返回
        """
        from apps.core.logger import opspilot_logger as logger
        import pandas as pd

        representation = super().to_representation(instance)

        # 处理 train_data：后端直接读取并解析 CSV
        if self.include_train_data and instance.train_data:
            try:
                # 读取 CSV 文件
                df = pd.read_csv(instance.train_data.open("rb"))

                # 转换为字典列表并添加索引
                data_list = df.to_dict("records")
                for i, row in enumerate(data_list):
                    row["index"] = i

                representation["train_data"] = data_list
                logger.info(
                    f"Successfully loaded train_data for instance {instance.id}: {len(data_list)} rows"
                )

            except Exception as e:
                logger.error(
                    f"Failed to read train_data for instance {instance.id}: {e}",
                    exc_info=True,
                )
                representation["train_data"] = []
                representation["error"] = f"读取训练数据失败: {str(e)}"
        elif not self.include_train_data:
            representation.pop("train_data", None)

        # 处理 metadata：S3JSONField 自动处理，直接返回对象
        if self.include_metadata and instance.metadata:
            # S3JSONField 会自动从 MinIO 读取并解压
            representation["metadata"] = instance.metadata
        elif not self.include_metadata:
            representation.pop("metadata", None)

        return representation


class ClassificationTrainJobSerializer(AuthSerializer):
    """分类任务训练作业序列化器"""

    permission_key = "dataset.classification_train_job"

    class Meta:
        model = ClassificationTrainJob
        fields = "__all__"
        extra_kwargs = {
            "config_url": {
                "required": False,
                "read_only": True,
                "help_text": "自动生成，无需手动提供",
            }
        }


class ClassificationDatasetReleaseSerializer(AuthSerializer):
    """分类任务数据集发布版本序列化器"""

    permission_key = "dataset.classification_dataset_release"

    # 添加只写字段用于接收文件ID
    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ClassificationDatasetRelease
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": False},  # 创建时可选，会自动生成
            "dataset_file": {"required": False},  # 创建时不需要直接提供文件
            "file_size": {"required": False},
            "status": {"required": False},
        }

    def create(self, validated_data):
        """
        自定义创建方法，支持从文件ID创建数据集发布版本
        """
        from apps.core.logger import opspilot_logger as logger

        # 提取文件ID
        train_file_id = validated_data.pop("train_file_id", None)
        val_file_id = validated_data.pop("val_file_id", None)
        test_file_id = validated_data.pop("test_file_id", None)

        # 如果提供了文件ID，则执行文件打包逻辑
        if train_file_id and val_file_id and test_file_id:
            return self._create_from_files(
                validated_data, train_file_id, val_file_id, test_file_id
            )
        else:
            # 否则使用标准创建（适用于直接上传ZIP文件的场景）
            return super().create(validated_data)

    def _create_from_files(
        self, validated_data, train_file_id, val_file_id, test_file_id
    ):
        """
        从训练数据文件ID创建数据集发布版本（异步）

        创建 pending 状态的记录，触发 Celery 任务进行异步处理
        """
        from apps.core.logger import opspilot_logger as logger
        from rest_framework import serializers

        dataset = validated_data.get("dataset")
        version = validated_data.get("version")
        name = validated_data.get("name")
        description = validated_data.get("description", "")

        try:
            # 验证文件是否存在
            train_obj = ClassificationTrainData.objects.get(
                id=train_file_id, dataset=dataset
            )
            val_obj = ClassificationTrainData.objects.get(
                id=val_file_id, dataset=dataset
            )
            test_obj = ClassificationTrainData.objects.get(
                id=test_file_id, dataset=dataset
            )

            # 检查是否已有相同版本的记录（幂等性保护）
            existing = (
                ClassificationDatasetRelease.objects.filter(
                    dataset=dataset, version=version
                )
                .exclude(status="failed")
                .first()
            )

            if existing:
                logger.info(
                    f"数据集版本已存在 - Dataset: {dataset.id}, Version: {version}, Status: {existing.status}"
                )
                return existing

            # 创建 pending 状态的发布记录
            validated_data["status"] = "pending"
            validated_data["file_size"] = 0
            validated_data["metadata"] = {}

            if not name:
                validated_data["name"] = f"{dataset.name}_v{version}"

            if not description:
                validated_data["description"] = (
                    f"从数据集文件手动发布: {train_obj.name}, {val_obj.name}, {test_obj.name}"
                )

            release = ClassificationDatasetRelease.objects.create(**validated_data)

            # 触发异步任务
            from apps.mlops.tasks.classification import publish_dataset_release_async

            try:
                result = publish_dataset_release_async.delay(
                    release.id, train_file_id, val_file_id, test_file_id
                )
                logger.info(
                    f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}, Task ID: {result.id}"
                )

            except Exception as task_error:
                logger.error(
                    f"投递 Celery 任务失败 - Release ID: {release.id}, Error: {str(task_error)}",
                    exc_info=True,
                )
                # 任务投递失败，更新发布状态为失败
                release.status = "failed"
                release.save(update_fields=["status"])
                raise serializers.ValidationError(
                    f"投递异步任务失败: {str(task_error)}"
                )

            return release

        except ClassificationTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建发布任务失败: {str(e)}")
