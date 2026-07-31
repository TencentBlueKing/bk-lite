from pathlib import Path


def test_algorithm_get_image_endpoints_use_localized_messages():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        assert source.count("mlops_message(request,") >= 2, module
        assert '"name 参数必填"' not in source, module
        assert '"未找到算法配置' not in source, module


def test_training_lifecycle_endpoints_use_localized_messages():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for message in (
            "训练任务已在运行中",
            "训练任务未在运行中",
            "训练任务已启动",
            "训练任务已停止",
            "数据集文件不存在",
            "训练配置文件不存在",
        ):
            assert f'"{message}"' not in source, f"{module}: {message}"


def test_dataset_release_archive_messages_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for message in (
            "归档成功",
            "恢复成功",
            "数据集版本已处于归档状态",
            "数据集版本已经是归档状态",
            "只能恢复已归档的数据集版本",
            "只能恢复归档状态的数据集版本",
        ):
            assert f'"{message}"' not in source, f"{module}: {message}"


def test_training_run_query_messages_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for message in (
            "分页参数必须为正整数",
            "未找到对应的MLflow实验",
            "未找到训练运行记录",
            "未找到对应的训练运行记录",
            "当前训练运行记录不允许删除",
        ):
            assert f'"{message}"' not in source, f"{module}: {message}"


def test_prediction_validation_messages_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for message in (
            "参数不能为空",
            "缺少参数",
            "必须是数组格式",
            "批量预测上限为",
            "单张图片 base64 长度超过上限",
        ):
            assert message not in source, f"{module}: {message}"


def test_algorithm_config_in_use_messages_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        assert "无法禁用：有" not in source, module
        assert "无法删除：有" not in source, module


def test_training_run_resource_error_responses_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    direct_response_prefixes = (
        '{"error": f"获取指标列表失败:',
        '{"error": f"获取指标历史数据失败:',
        '{"error": f"获取运行参数失败:',
        '{"error": f"获取模型版本列表失败:',
        '{"error": f"下载模型失败:',
    )
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for prefix in direct_response_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_dataset_release_and_serving_operation_error_responses_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    direct_response_prefixes = (
        '{"error": f"下载失败:',
        '{"error": f"归档失败:',
        '{"error": f"恢复失败:',
        '{"error": f"容器已存在但同步状态失败:',
        '{"error": f"启动服务失败:',
        '{"error": f"停止服务失败:',
        '{"error": f"删除容器失败:',
    )
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for prefix in direct_response_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_serving_prediction_error_responses_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    direct_response_prefixes = (
        '{"error": f"预测失败:',
        '{"error": f"端口 ',
        '{"error": f"模型 ',
        '{"error": f"无法连接到预测服务:',
        '{"error": f"无法连接推理服务:',
        '{"error": f"预测调用失败:',
        '{"error": f"推理服务错误:',
        '{"error": f"推理失败:',
        '{"error": "服务未启动或容器信息不可用"',
    )
    for module in (
        "anomaly_detection.py",
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for prefix in direct_response_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_training_data_and_configuration_error_responses_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    direct_response_prefixes = (
        '{"error": f"删除失败:',
        '{"error": f"获取失败:',
        '{"error": "训练数据文件不存在"',
        '{"error": "Metadata 不存在"',
        '{"error": "系统配置错误，请联系管理员"',
        '{"error": f"系统配置错误:',
        '{"error": f"配置更新未生效，旧服务保持运行:',
    )
    for module in (
        "timeseries_predict.py",
        "log_clustering.py",
        "classification.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for prefix in direct_response_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_common_dataset_release_serializer_errors_use_i18n():
    serializers_dir = Path(__file__).resolve().parents[1] / "serializers"
    direct_error_prefixes = (
        'f"数据集 {dataset.name} 的版本 {version} 已存在"',
        'f"数据集 {dataset.name} 的版本 {version} 已存在或正在处理中"',
        '"投递异步任务失败"',
        'f"训练数据文件不存在或不属于该数据集"',
        '"创建发布任务失败"',
        '"创建训练任务时必须指定数据集版本"',
    )
    for module in (
        "anomaly_detection.py",
        "classification.py",
        "log_clustering.py",
        "timeseries_predict.py",
    ):
        source = (serializers_dir / module).read_text(encoding="utf-8")
        for prefix in direct_error_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_text_training_data_serializer_errors_use_i18n():
    serializers_dir = Path(__file__).resolve().parents[1] / "serializers"
    direct_error_prefixes = (
        'f"缺少必需列:',
        '"\'value\'列包含空值"',
        '"\'text\'列包含空值"',
        '"\'label\'列包含空值"',
        'f"无效的CSV格式:',
        'f"读取训练数据失败:',
    )
    for module in (
        "anomaly_detection.py",
        "classification.py",
        "timeseries_predict.py",
    ):
        source = (serializers_dir / module).read_text(encoding="utf-8")
        for prefix in direct_error_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_image_dataset_release_and_train_config_errors_use_i18n():
    serializers_dir = Path(__file__).resolve().parents[1] / "serializers"
    direct_error_prefixes = (
        '"版本号格式应为 vX.Y.Z，例如：v1.0.0"',
        'f"数据集 {dataset.name} 的版本 {version} 已存在或正在处理中"',
        '"投递异步任务失败"',
        'f"训练数据文件不存在或不属于该数据集"',
        '"创建发布任务失败"',
        '"必须提供数据集文件或训练数据文件ID"',
        'f"数据集 {dataset.name} 的版本 {version} 已存在"',
        '"hyperopt_config 必须是字典格式"',
        '"hyperopt_config 必须包含 hyperparams 字段"',
        '"hyperparams 必须是字典格式"',
        '"模型版本必须是 \'latest\' 或正整数（如：1, 2, 3）"',
    )
    for module in ("image_classification.py", "object_detection.py"):
        source = (serializers_dir / module).read_text(encoding="utf-8")
        for prefix in direct_error_prefixes:
            assert prefix not in source, f"{module}: {prefix}"


def test_object_detection_metadata_errors_use_i18n():
    source = (Path(__file__).resolve().parents[1] / "serializers" / "object_detection.py").read_text(encoding="utf-8")
    for prefix in (
        '"metadata 必须是字典格式"',
        'f"metadata 缺少必需字段:',
        '"metadata.format 必须为 \'YOLO\'"',
        '"metadata.classes 必须是数组"',
        '"metadata.classes 不能为空"',
        '"metadata.classes 中的所有元素必须是字符串"',
        '"metadata.num_classes 必须是正整数"',
        'f"metadata.num_classes (',
        '"metadata.num_images 必须是正整数"',
        '"metadata.labels 必须是对象"',
        'f"metadata.labels 的键必须是字符串',
        'f"图片 \'{img_name}\' 的第',
        '"metadata.statistics 必须是对象"',
        '"metadata.statistics.total_annotations 必须是非负整数"',
        '"metadata.statistics.class_distribution 必须是对象"',
    ):
        assert prefix not in source, prefix


def test_serving_creation_and_update_response_messages_use_i18n():
    views_dir = Path(__file__).resolve().parents[1] / "views"
    direct_message_prefixes = (
        'response.data["message"] = "服务已创建但启动失败：环境变量未配置"',
        'response.data["message"] = f"服务已创建但启动失败：',
        'response.data["message"] = "服务已创建并启动"',
        'response.data["message"] = "服务已创建，检测到容器已存在并同步容器状态"',
        'response.data["message"] = "服务已创建但启动失败"',
        'response.data["message"] = f"服务已创建但启动失败:',
        'response.data["message"] = f"服务已创建但启动异常:',
        'response.data["message"] = "配置已更新并重启服务"',
        'response.data["message"] = f"配置已更新但重启失败:',
    )
    for module in (
        "anomaly_detection.py",
        "classification.py",
        "log_clustering.py",
        "timeseries_predict.py",
        "image_classification.py",
        "object_detection.py",
    ):
        source = (views_dir / module).read_text(encoding="utf-8")
        for prefix in direct_message_prefixes:
            assert prefix not in source, f"{module}: {prefix}"
