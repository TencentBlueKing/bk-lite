"""模型归档的大输入内存边界回归测试。"""

import asyncio
import random
import tempfile
import tracemalloc
from types import SimpleNamespace

import pydantic.root_model  # noqa
import pytest
from django.http import FileResponse

from apps.mlops.utils import mlflow_service as ms


async def _consume_response(response):
    total_size = 0
    async for chunk in response:
        total_size += len(chunk)
    return total_size


async def _consume_one_chunk_then_disconnect(response):
    iterator = response.__aiter__()
    await iterator.__anext__()
    await iterator.aclose()


def _measure_asgi_response(response):
    tracemalloc.start()
    streamed_size = asyncio.run(_consume_response(response))
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return streamed_size, peak_bytes


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


def test_model_download_response_keeps_asgi_stream_off_heap():
    input_size = 4 * 1024 * 1024
    payload = random.Random(4244).randbytes(input_size)

    baseline_archive = tempfile.TemporaryFile(mode="w+b")
    baseline_archive.write(payload)
    baseline_archive.seek(0)
    baseline_response = FileResponse(baseline_archive, content_type="application/zip")
    with pytest.warns(Warning, match="consume synchronous"):
        baseline_size, baseline_peak_bytes = _measure_asgi_response(baseline_response)
    baseline_response.close()

    archive = tempfile.TemporaryFile(mode="w+b")
    archive.write(payload)
    archive.seek(0)

    response = ms.build_model_download_response(archive, "model_r1.zip")
    streamed_size, peak_bytes = _measure_asgi_response(response)

    try:
        assert response.is_async
        assert baseline_size == input_size
        assert streamed_size == input_size
        assert baseline_peak_bytes >= input_size
        assert peak_bytes < input_size, f"4 MiB ASGI 响应的 Python 堆峰值为 {peak_bytes} bytes"
    finally:
        response.close()

    assert archive.closed


def test_model_download_response_close_cleans_unconsumed_archive():
    archive = tempfile.TemporaryFile(mode="w+b")
    archive.write(b"zipdata")
    archive.seek(0)

    response = ms.build_model_download_response(archive, "model_r1.zip")
    response.close()

    assert archive.closed


def test_model_download_response_preserves_file_response_basename():
    archive = tempfile.TemporaryFile(mode="w+b")
    archive.write(b"zipdata")
    archive.seek(0)

    response = ms.build_model_download_response(archive, "team/model_r1.zip")
    try:
        assert response["Content-Disposition"] == 'attachment; filename="model_r1.zip"'
    finally:
        response.close()


def test_model_download_response_disconnect_closes_archive():
    archive = tempfile.TemporaryFile(mode="w+b")
    archive.write(b"x" * (128 * 1024))
    archive.seek(0)

    response = ms.build_model_download_response(archive, "model_r1.zip")
    asyncio.run(_consume_one_chunk_then_disconnect(response))

    assert archive.closed
