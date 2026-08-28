import traceback

from core.logger import safe_exception_info, safe_log_value


def test_safe_log_value_returns_bounded_single_line_copy_without_changing_source():
    source = "target\r\nforged=" + "x" * 300

    rendered = safe_log_value(source, max_length=32)

    assert rendered == "target\\r\\nforged=" + "x" * 15
    assert "\r" not in rendered
    assert "\n" not in rendered
    assert source.startswith("target\r\n")


def test_safe_exception_info_preserves_traceback_but_omits_sensitive_original_message():
    secret = "traceback-" + "secret-sentinel"
    error = None
    try:
        raise RuntimeError("password=" + secret)
    except RuntimeError as caught:
        error = caught

    exc_type, safe_error, safe_traceback = safe_exception_info(error)
    formatted = "".join(traceback.format_exception(exc_type, safe_error, safe_traceback))

    assert safe_traceback is error.__traceback__
    assert "test_safe_exception_info_preserves_traceback" in formatted
    assert "RuntimeError" in str(safe_error)
    assert "traceback-secret-sentinel" not in formatted
    assert str(error) == "password=traceback-secret-sentinel"
