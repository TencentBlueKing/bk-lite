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
            "数据集文件不存在",
            "训练配置文件不存在",
        ):
            assert f'"{message}"' not in source, f"{module}: {message}"
