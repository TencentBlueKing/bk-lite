"""模型归档的大输入内存边界回归测试。"""

import random
import tracemalloc
from types import SimpleNamespace

import pydantic.root_model  # noqa

from apps.mlops.utils import mlflow_service as ms


def test_download_model_artifact_keeps_large_zip_off_heap(tmp_path, mocker):
    input_size = 4 * 1024 * 1024
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(random.Random(4244).randbytes(input_size))

    client = SimpleNamespace(download_artifacts=lambda run_id, artifact_path, dst_path: str(model_file))
    mocker.patch("apps.mlops.utils.mlflow_service.get_mlflow_client", return_value=client)

    tracemalloc.start()
    archive = ms.download_model_artifact("r1", "model.bin")
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    try:
        assert peak_bytes < input_size, f"4 MiB 输入的 Python 堆峰值为 {peak_bytes} bytes"
    finally:
        archive.close()
