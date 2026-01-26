from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.timeseries_predict import *
from apps.core.logger import opspilot_logger as logger


class TimeSeriesPredictDatasetSerializer(AuthSerializer):
    """时间序列预测数据集序列化器"""

    permission_key = "dataset.timeseries_predict_dataset"

    class Meta:
        model = TimeSeriesPredictDataset
        fields = "__all__"


class TimeSeriesPredictTrainJobSerializer(AuthSerializer):
    """
    时间序列预测训练任务序列化器

    使用双字段方案：
    - hyperopt_config: JSONField，存储在数据库，供API快速返回
    - config_url: FileField，自动同步到MinIO（Model.save()处理）
    """

    permission_key = "dataset.timeseries_predict_train_job"

    class Meta:
        model = TimeSeriesPredictTrainJob
        fields = "__all__"
        extra_kwargs = {
            "config_url": {
                "write_only": True,  # 前端不需要看到 MinIO 路径
                "required": False,
            }
        }

    def validate(self, attrs):
        """
        验证创建时 dataset_version 必须传入
        """
        # 只在创建时验证（更新时不强制要求）
        if not self.instance and not attrs.get("dataset_version"):
            raise serializers.ValidationError(
                {"dataset_version": "创建训练任务时必须指定数据集版本"}
            )
        return super().validate(attrs)


class TimeSeriesPredictTrainDataSerializer(AuthSerializer):
    """时间序列预测训练数据序列化器"""

    permission_key = "dataset.timeseries_predict_train_data"

    class Meta:
        model = TimeSeriesPredictTrainData
        fields = "__all__"

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
            required_columns = ["timestamp", "value"]
            missing = set(required_columns) - set(df.columns)
            if missing:
                raise serializers.ValidationError(f"缺少必需列: {', '.join(missing)}")

            # 检查数据类型
            if df["value"].isnull().any():
                raise serializers.ValidationError("'value'列包含空值")

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

                # 🔥 处理 timestamp 字段：转换为 Unix 时间戳（秒）
                if "timestamp" in df.columns:
                    try:
                        # 尝试解析各种日期格式
                        df["timestamp"] = pd.to_datetime(df["timestamp"])
                        # 转换为 Unix 时间戳（秒）
                        df["timestamp"] = (
                            df["timestamp"].astype("int64") / 1e9
                        ).astype("int64")
                    except Exception as e:
                        logger.warning(f"Failed to parse timestamp column: {e}")
                        # 如果解析失败，尝试保持原值

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


class TimeSeriesPredictServingSerializer(AuthSerializer):
    """时间序列预测服务序列化器"""

    permission_key = "dataset.timeseries_predict_serving"

    class Meta:
        model = TimeSeriesPredictServing
        fields = "__all__"


class TimeSeriesPredictDatasetReleaseSerializer(AuthSerializer):
    """时间序列预测数据集发布版本序列化器"""

    permission_key = "dataset.timeseries_predict_dataset_release"

    # 添加只写字段用于接收文件ID
    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = TimeSeriesPredictDatasetRelease
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
        dataset = validated_data.get("dataset")
        version = validated_data.get("version")
        name = validated_data.get("name")
        description = validated_data.get("description", "")

        try:
            # 验证文件是否存在
            train_obj = TimeSeriesPredictTrainData.objects.get(
                id=train_file_id, dataset=dataset
            )
            val_obj = TimeSeriesPredictTrainData.objects.get(
                id=val_file_id, dataset=dataset
            )
            test_obj = TimeSeriesPredictTrainData.objects.get(
                id=test_file_id, dataset=dataset
            )

            # 检查是否已有相同版本的记录（幂等性保护）
            existing = (
                TimeSeriesPredictDatasetRelease.objects.filter(
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

            release = TimeSeriesPredictDatasetRelease.objects.create(**validated_data)

            # 触发异步任务
            from apps.mlops.tasks.timeseries import publish_dataset_release_async

            publish_dataset_release_async.delay(
                release.id, train_file_id, val_file_id, test_file_id
            )

            logger.info(
                f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}"
            )

            return release

        except TimeSeriesPredictTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建发布任务失败: {str(e)}")
