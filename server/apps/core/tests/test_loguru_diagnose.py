"""Loguru diagnose must stay off so traceback frames do not render locals."""

from io import StringIO

from loguru import logger as loguru_logger

from apps.core.logger import configure_loguru


def test_configure_loguru_disables_diagnose_and_hides_frame_locals():
    sink = StringIO()
    configure_loguru(sink=sink)
    try:
        for handler in loguru_logger._core.handlers.values():
            assert handler._exception_formatter._diagnose is False

        sentinel = "SENTINEL_PWD_5951_TEST"

        def boom():
            conn_str = f"PWD={sentinel}"
            raise RuntimeError("connect failed")

        try:
            boom()
        except RuntimeError:
            loguru_logger.exception("MSSQL数据库连接失败")

        output = sink.getvalue()
        assert "MSSQL数据库连接失败" in output
        assert "connect failed" in output
        assert sentinel not in output
        assert "conn_str" not in output
    finally:
        configure_loguru()
