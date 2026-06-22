"""
纯函数测试：验证 count_csv_samples / count_txt_samples 流式实现的正确性。

这些测试不依赖 Django ORM / settings，通过 importlib 直接加载被测模块，
使用轻量 harness 注入最小依赖桩（参考 CLAUDE.md Phase 5.4 Django-free 模式）。

回归标准（revert-fail 准则）：
  - 将 count_csv_samples / count_txt_samples 改回接收 bytes 的旧实现，
    TestSignatures 因签名不匹配而失败；
  - 将流式 iter 改回 file_content = f.read()，
    TestPublishDatasetReleaseBaseNoFullRead 中的源码静态断言失败。
"""

# ruff: noqa: E402 — 需在 stubs 安装后再 import 被测模块

import importlib.util
import inspect
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 最小依赖桩注入（Django-free）
# ---------------------------------------------------------------------------

def _stub(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _install_stubs():
    # django.*
    django_mod = _stub("django")
    db_mod = _stub("django.db")
    models_mod = _stub("django.db.models")
    models_mod.Model = object
    trans_mod = _stub("django.db.transaction")
    trans_mod.atomic = lambda: (lambda f: f)
    db_mod.models = models_mod
    db_mod.transaction = trans_mod
    django_mod.db = db_mod

    utils_mod = _stub("django.utils")
    tz_mod = _stub("django.utils.timezone")
    tz_mod.now = lambda: None
    utils_mod.timezone = tz_mod
    django_mod.utils = utils_mod

    # django_minio_backend
    minio_mod = _stub("django_minio_backend")
    minio_mod.MinioBackend = object
    minio_mod.iso_date_prefix = lambda *a, **kw: ""

    # apps.core.logger
    _stub("apps")
    _stub("apps.core")
    core_logger = _stub("apps.core.logger")
    import logging
    core_logger.mlops_logger = logging.getLogger("mlops")


_install_stubs()


def _load_base() -> types.ModuleType:
    base_path = (
        Path(__file__).resolve().parents[3] / "apps" / "mlops" / "tasks" / "base.py"
    )
    spec = importlib.util.spec_from_file_location("_mlops_tasks_base", base_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_base = _load_base()
count_csv_samples = _base.count_csv_samples
count_txt_samples = _base.count_txt_samples
DatasetPublishConfig = _base.DatasetPublishConfig


# ---------------------------------------------------------------------------
# 签名校验：确保函数接受 Path（修复的核心契约）
# ---------------------------------------------------------------------------

class TestSignatures:
    """若 revert 回旧的 bytes 签名，这些测试失败。"""

    def test_count_csv_samples_accepts_path(self):
        sig = inspect.signature(count_csv_samples)
        param = list(sig.parameters.values())[0]
        assert param.annotation is Path, (
            f"count_csv_samples 第一个参数应标注 Path，实际：{param.annotation!r}。"
            "旧实现接收 bytes，已不再符合流式要求。"
        )

    def test_count_txt_samples_accepts_path(self):
        sig = inspect.signature(count_txt_samples)
        param = list(sig.parameters.values())[0]
        assert param.annotation is Path, (
            f"count_txt_samples 第一个参数应标注 Path，实际：{param.annotation!r}。"
        )

    def test_dataset_publish_config_count_samples_hint_uses_path(self):
        from typing import get_type_hints
        hints = get_type_hints(DatasetPublishConfig)
        hint_str = str(hints.get("count_samples", ""))
        assert "Path" in hint_str, (
            f"DatasetPublishConfig.count_samples 类型提示应含 Path，实际：{hint_str}"
        )
        assert "bytes" not in hint_str, (
            f"DatasetPublishConfig.count_samples 不应含 bytes（旧接口已废弃），实际：{hint_str}"
        )


# ---------------------------------------------------------------------------
# count_csv_samples 正确性
# ---------------------------------------------------------------------------

class TestCountCsvSamples:
    def _write(self, tmp_path: Path, content: bytes) -> Path:
        p = tmp_path / "data.csv"
        p.write_bytes(content)
        return p

    def test_basic_csv(self, tmp_path):
        """1 行表头 + 3 行数据 → 3 样本"""
        content = b"col1,col2\nrow1,1\nrow2,2\nrow3,3\n"
        assert count_csv_samples(self._write(tmp_path, content)) == 3

    def test_header_only(self, tmp_path):
        content = b"col1,col2\n"
        assert count_csv_samples(self._write(tmp_path, content)) == 0

    def test_empty_file(self, tmp_path):
        assert count_csv_samples(self._write(tmp_path, b"")) == 0

    def test_no_trailing_newline(self, tmp_path):
        # header\nrow1\nrow2  → 2 换行，减 1 header = 1
        content = b"header\nrow1\nrow2"
        assert count_csv_samples(self._write(tmp_path, content)) == 1

    def test_large_file_streaming(self, tmp_path):
        """>64KB 文件：分块计数应与预期一致"""
        header = b"timestamp,value\n"
        row = b"2024-01-01T00:00:00,42.0\n"
        rows = row * 5000  # ~125 KB
        content = header + rows
        assert len(content) > 65536
        assert count_csv_samples(self._write(tmp_path, content)) == 5000

    def test_chunk_boundary(self, tmp_path):
        """换行恰好在 chunk 边界"""
        chunk = _base._STREAM_CHUNK_SIZE
        # header(2B) + (chunk-2)个'x' + '\n' + 'data\n'
        content = b"h\n" + b"x" * (chunk - 2) + b"\ndata\n"
        result = count_csv_samples(self._write(tmp_path, content))
        assert result >= 1


# ---------------------------------------------------------------------------
# count_txt_samples 正确性
# ---------------------------------------------------------------------------

class TestCountTxtSamples:
    def _write(self, tmp_path: Path, content: bytes) -> Path:
        p = tmp_path / "data.txt"
        p.write_bytes(content)
        return p

    def test_basic_txt(self, tmp_path):
        content = b"line1\nline2\nline3\n"
        assert count_txt_samples(self._write(tmp_path, content)) == 3

    def test_no_trailing_newline(self, tmp_path):
        content = b"line1\nline2\nline3"
        assert count_txt_samples(self._write(tmp_path, content)) == 3

    def test_empty_file(self, tmp_path):
        assert count_txt_samples(self._write(tmp_path, b"")) == 0

    def test_single_line_with_newline(self, tmp_path):
        assert count_txt_samples(self._write(tmp_path, b"only-line\n")) == 1

    def test_single_line_no_newline(self, tmp_path):
        assert count_txt_samples(self._write(tmp_path, b"only-line")) == 1

    def test_large_txt_streaming(self, tmp_path):
        lines = b"".join(f"entry-{i}\n".encode() for i in range(10000))
        assert len(lines) > 65536
        assert count_txt_samples(self._write(tmp_path, lines)) == 10000


# ---------------------------------------------------------------------------
# 源码静态验证：publish_dataset_release_base 不再全量加载
# ---------------------------------------------------------------------------

class TestPublishDatasetReleaseBaseNoFullRead:
    _source: str = (
        Path(__file__).resolve().parents[3] / "apps" / "mlops" / "tasks" / "base.py"
    ).read_text(encoding="utf-8")

    def test_streaming_write_pattern_present(self):
        """流式写入模式存在"""
        assert (
            'iter(lambda: src.read(_STREAM_CHUNK_SIZE), b"")' in self._source
            or "iter(lambda: src.read(_STREAM_CHUNK_SIZE), b'')" in self._source
        ), "publish_dataset_release_base 应使用 iter(lambda: src.read(CHUNK), b\"\") 流式写文件"

    def test_full_read_pattern_absent(self):
        """全量读取模式已消除"""
        assert "file_content = f.read()" not in self._source, (
            "仍存在 `file_content = f.read()` 全量加载！修复要求已消除此模式。"
        )

    def test_count_samples_called_with_path(self):
        """count_samples 以 Path 调用"""
        assert "config.count_samples(local_file_path)" in self._source, (
            "count_samples 应传入 local_file_path (Path)，而非 file_content (bytes)"
        )
        assert "config.count_samples(file_content)" not in self._source, (
            "仍在用 file_content (bytes) 调用 count_samples（旧模式未清除）"
        )
