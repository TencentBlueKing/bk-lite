from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.object_detection import (
    ObjectDetectionDataset,
    ObjectDetectionTrainData,
    ObjectDetectionDatasetRelease,
    ObjectDetectionTrainJob,
    ObjectDetectionServing,
)
from rest_framework import serializers
from apps.core.logger import mlops_logger as logger


class ObjectDetectionDatasetSerializer(AuthSerializer):
    """目标检测数据集序列化器"""

    permission_key = "dataset.object_detection_dataset"

    class Meta:
        model = ObjectDetectionDataset
        fields = "__all__"


class ObjectDetectionTrainDataSerializer(AuthSerializer):
    """目标检测训练数据序列化器（重构为 ZIP 上传）"""

    permission_key = "dataset.object_detection_train_data"

    class Meta:
        model = ObjectDetectionTrainData
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

    def to_representation(self, instance):
        """自定义返回数据，根据参数动态控制字段"""
        representation = super().to_representation(instance)

        # 根据查询参数控制大文件字段返回
        if not self.include_train_data:
            representation.pop("train_data", None)
        if not self.include_metadata:
            representation.pop("metadata", None)

        return representation

    def validate_metadata(self, value):
        """验证 metadata 格式是否符合 YOLO 标准"""
        if not value:
            # 允许空 metadata（可能后续填充）
            return value

        if not isinstance(value, dict):
            raise serializers.ValidationError("metadata 必须是字典格式")

        # 验证必需字段
        required_fields = ["format", "classes", "num_classes", "num_images", "labels"]
        missing_fields = [field for field in required_fields if field not in value]
        if missing_fields:
            raise serializers.ValidationError(
                f"metadata 缺少必需字段: {', '.join(missing_fields)}"
            )

        # 验证 format
        if value.get("format") != "YOLO":
            raise serializers.ValidationError("metadata.format 必须为 'YOLO'")

        # 验证 classes
        classes = value.get("classes")
        if not isinstance(classes, list):
            raise serializers.ValidationError("metadata.classes 必须是数组")
        if not classes:
            raise serializers.ValidationError("metadata.classes 不能为空")
        if not all(isinstance(c, str) for c in classes):
            raise serializers.ValidationError(
                "metadata.classes 中的所有元素必须是字符串"
            )

        # 验证 num_classes
        num_classes = value.get("num_classes")
        if not isinstance(num_classes, int) or num_classes <= 0:
            raise serializers.ValidationError("metadata.num_classes 必须是正整数")
        if num_classes != len(classes):
            raise serializers.ValidationError(
                f"metadata.num_classes ({num_classes}) 与 classes 数组长度 ({len(classes)}) 不匹配"
            )

        # 验证 num_images
        num_images = value.get("num_images")
        if not isinstance(num_images, int) or num_images <= 0:
            raise serializers.ValidationError("metadata.num_images 必须是正整数")

        # 验证 labels
        labels = value.get("labels")
        if not isinstance(labels, dict):
            raise serializers.ValidationError("metadata.labels 必须是对象")

        # 验证每个图片的标注
        for img_name, annotations in labels.items():
            if not isinstance(img_name, str):
                raise serializers.ValidationError(
                    f"metadata.labels 的键必须是字符串，发现: {type(img_name).__name__}"
                )

            if not isinstance(annotations, list):
                raise serializers.ValidationError(f"图片 '{img_name}' 的标注必须是数组")

            # 验证每个标注框
            for idx, ann in enumerate(annotations):
                if not isinstance(ann, dict):
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注必须是对象"
                    )

                # 验证必需字段
                ann_required = [
                    "class_id",
                    "class_name",
                    "x_center",
                    "y_center",
                    "width",
                    "height",
                ]
                ann_missing = [field for field in ann_required if field not in ann]
                if ann_missing:
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注缺少字段: {', '.join(ann_missing)}"
                    )

                # 验证 class_id
                class_id = ann.get("class_id")
                if not isinstance(class_id, int):
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_id 必须是整数"
                    )
                if class_id < 0 or class_id >= num_classes:
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_id ({class_id}) 超出范围 [0, {num_classes - 1}]"
                    )

                # 验证 class_name
                class_name = ann.get("class_name")
                if not isinstance(class_name, str):
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_name 必须是字符串"
                    )
                if class_id < len(classes) and class_name != classes[class_id]:
                    raise serializers.ValidationError(
                        f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_name '{class_name}' 与 classes[{class_id}] '{classes[class_id]}' 不匹配"
                    )

                # 验证坐标值（归一化，范围 0-1）
                coord_fields = ["x_center", "y_center", "width", "height"]
                for coord_field in coord_fields:
                    coord_value = ann.get(coord_field)
                    if not isinstance(coord_value, (int, float)):
                        raise serializers.ValidationError(
                            f"图片 '{img_name}' 的第 {idx + 1} 个标注: {coord_field} 必须是数字"
                        )
                    if coord_value < 0 or coord_value > 1:
                        raise serializers.ValidationError(
                            f"图片 '{img_name}' 的第 {idx + 1} 个标注: {coord_field} ({coord_value}) 必须在 [0, 1] 范围内"
                        )

        # 验证 statistics（可选，但如果存在则验证格式）
        if "statistics" in value:
            statistics = value["statistics"]
            if not isinstance(statistics, dict):
                raise serializers.ValidationError("metadata.statistics 必须是对象")

            # 验证 total_annotations
            if "total_annotations" in statistics:
                total_annotations = statistics["total_annotations"]
                if not isinstance(total_annotations, int) or total_annotations < 0:
                    raise serializers.ValidationError(
                        "metadata.statistics.total_annotations 必须是非负整数"
                    )

            # 验证 class_distribution
            if "class_distribution" in statistics:
                class_distribution = statistics["class_distribution"]
                if not isinstance(class_distribution, dict):
                    raise serializers.ValidationError(
                        "metadata.statistics.class_distribution 必须是对象"
                    )

        logger.info(
            f"metadata 验证通过: {num_images} 张图片, {num_classes} 个类别, {len(labels)} 个标注文件"
        )

        return value


class ObjectDetectionDatasetReleaseSerializer(AuthSerializer):
    """目标检测数据集发布版本序列化器"""

    permission_key = "dataset.object_detection_dataset_release"

    dataset_name = serializers.CharField(source="dataset.name", read_only=True)

    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ObjectDetectionDatasetRelease
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": False},
            "dataset_file": {"required": False},
            "file_size": {"required": False},
            "status": {"required": False},
        }

    def validate_version(self, value):
        """验证版本号格式"""
        import re

        if not re.match(r"^v\d+\.\d+\.\d+$", value):
            raise serializers.ValidationError("版本号格式应为 vX.Y.Z，例如：v1.0.0")
        return value

    def create(self, validated_data):
        """自定义创建方法，支持从文件ID创建数据集发布版本"""
        train_file_id = validated_data.pop("train_file_id", None)
        val_file_id = validated_data.pop("val_file_id", None)
        test_file_id = validated_data.pop("test_file_id", None)

        if train_file_id and val_file_id and test_file_id:
            return self._create_from_files(
                validated_data, train_file_id, val_file_id, test_file_id
            )
        else:
            return super().create(validated_data)

    def _create_from_files(
        self, validated_data, train_file_id, val_file_id, test_file_id
    ):
        """从训练数据文件ID创建数据集发布版本（异步）"""
        dataset = validated_data.get("dataset")
        version = validated_data.get("version")
        name = validated_data.get("name")
        description = validated_data.get("description", "")

        try:
            train_obj = ObjectDetectionTrainData.objects.get(
                id=train_file_id, dataset=dataset
            )
            val_obj = ObjectDetectionTrainData.objects.get(
                id=val_file_id, dataset=dataset
            )
            test_obj = ObjectDetectionTrainData.objects.get(
                id=test_file_id, dataset=dataset
            )

            existing = (
                ObjectDetectionDatasetRelease.objects.filter(
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

            validated_data["status"] = "pending"
            validated_data["file_size"] = 0
            validated_data["metadata"] = {}

            if not name:
                validated_data["name"] = f"{dataset.name}_{version}"

            if not description:
                validated_data["description"] = (
                    f"从数据集文件自动发布: {train_obj.name}, {val_obj.name}, {test_obj.name}"
                )

            release = ObjectDetectionDatasetRelease.objects.create(**validated_data)

            from apps.mlops.tasks.object_detection import publish_dataset_release_async

            publish_dataset_release_async.delay(
                release.id, train_file_id, val_file_id, test_file_id
            )

            logger.info(
                f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}"
            )

            return release

        except ObjectDetectionTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建发布任务失败: {str(e)}")

    def validate(self, attrs):
        """验证数据集和版本的唯一性"""
        dataset = attrs.get("dataset")
        version = attrs.get("version")

        train_file_id = attrs.get("train_file_id")
        val_file_id = attrs.get("val_file_id")
        test_file_id = attrs.get("test_file_id")

        if not (train_file_id and val_file_id and test_file_id):
            if not attrs.get("dataset_file"):
                raise serializers.ValidationError(
                    {"dataset_file": "必须提供数据集文件或训练数据文件ID"}
                )

        if dataset and version:
            if self.instance:
                exists = (
                    ObjectDetectionDatasetRelease.objects.filter(
                        dataset=dataset, version=version
                    )
                    .exclude(pk=self.instance.pk)
                    .exists()
                )
            else:
                exists = ObjectDetectionDatasetRelease.objects.filter(
                    dataset=dataset, version=version
                ).exists()

            if exists:
                raise serializers.ValidationError(
                    {"version": f"数据集 {dataset.name} 的版本 {version} 已存在"}
                )

        return attrs


class ObjectDetectionTrainJobSerializer(AuthSerializer):
    """目标检测训练任务序列化器"""

    permission_key = "train_tasks.object_detection_train_job"

    dataset_version_name = serializers.CharField(
        source="dataset_version.name", read_only=True
    )
    config_url_display = serializers.SerializerMethodField()

    class Meta:
        model = ObjectDetectionTrainJob
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

        if "hyperparams" not in value:
            raise serializers.ValidationError(
                "hyperopt_config 必须包含 hyperparams 字段"
            )

        hyperparams = value["hyperparams"]
        if not isinstance(hyperparams, dict):
            raise serializers.ValidationError("hyperparams 必须是字典格式")

        return value

    def create(self, validated_data):
        """创建训练任务，自动设置为 pending 状态"""
        validated_data["status"] = "pending"
        return super().create(validated_data)


class ObjectDetectionServingSerializer(AuthSerializer):
    """目标检测服务序列化器"""

    permission_key = "serving.object_detection_serving"

    train_job_name = serializers.CharField(source="train_job.name", read_only=True)
    train_job_algorithm = serializers.CharField(
        source="train_job.algorithm", read_only=True
    )
    actual_port = serializers.SerializerMethodField()
    container_status = serializers.SerializerMethodField()

    class Meta:
        model = ObjectDetectionServing
        fields = "__all__"
        extra_kwargs = {"container_info": {"read_only": True}}

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
            raise serializers.ValidationError(
                "模型版本必须是 'latest' 或正整数（如：1, 2, 3）"
            )
        return value
