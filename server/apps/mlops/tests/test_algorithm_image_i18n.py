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
