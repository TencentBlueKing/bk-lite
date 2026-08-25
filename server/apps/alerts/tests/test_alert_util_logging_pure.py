import pytest

from apps.alerts.utils import util

pytestmark = pytest.mark.unit


def test_str_to_md5_encoding_failure_uses_logger_without_stdout(mocker, capsys):
    warning = mocker.patch.object(util.logger, "warning")

    assert util.str_to_md5("\udcff") == ""

    assert capsys.readouterr().out == ""
    warning.assert_called_once_with(
        "event=string_hash_encoding_failed encoding=%s error_type=%s",
        "utf-8",
        "UnicodeEncodeError",
    )
