"""Issue #4248 CSV 形状、解析与对象放大契约。"""

import pytest
from rest_framework import serializers

from apps.mlops.tests._issue_4248_inline_helpers import CSV_SERIALIZER_CASES, _install_file_reader, _instances, _request

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(("suffix", "basename"), CSV_SERIALIZER_CASES)
def test_inline_csv_rejects_wide_header_before_pandas_expansion(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"first,second,third\n1,2,3\n",
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["reason"] == "csv_columns"
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(
    "content",
    (
        b'first"alias,second,third\n1,2,3\n',
        b"\n \t\nfirst,second,third\n",
    ),
)
def test_inline_csv_column_scan_matches_pandas_header_selection(
    monkeypatch,
    mlops_user,
    content,
):
    import pandas as pd

    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(monkeypatch, instances, content)
    pandas_calls = []

    def unexpected_pandas_call(*_args, **_kwargs):
        pandas_calls.append(True)
        raise AssertionError("超宽 CSV 必须在 Pandas 前拒绝")

    monkeypatch.setattr(pd, "read_csv", unexpected_pandas_call)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["reason"] == "csv_columns"
    assert pandas_calls == []
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(
    "content",
    (
        b"first,second\n1,2,3\n",
        b'first,second\n"1,2",3,4\n',
    ),
)
def test_inline_csv_rejects_wide_data_row_before_pandas_expansion(
    monkeypatch,
    mlops_user,
    content,
):
    import pandas as pd

    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        content,
    )
    pandas_calls = []

    def unexpected_pandas_call(*_args, **_kwargs):
        pandas_calls.append(True)
        raise AssertionError("超宽数据行必须在 Pandas 前拒绝")

    monkeypatch.setattr(pd, "read_csv", unexpected_pandas_call)

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["reason"] == "csv_columns"
    assert pandas_calls == []
    assert reads == ["fixtures/0.data"]


def test_inline_csv_small_ragged_row_keeps_pandas_contract(
    monkeypatch,
    mlops_user,
):
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"text,label\nleft,middle,right\n",
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert data[0]["train_data"][0]["text"] == "middle"
    assert data[0]["train_data"][0]["label"] == "right"
    assert reads == ["fixtures/0.data"]


def test_inline_csv_quoted_newline_and_escaped_quote_keep_record_shape(
    monkeypatch,
    mlops_user,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b'first,second\n"line one\nline two","quoted ""value"""\n',
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert data[0]["train_data"][0]["first"] == "line one\nline two"
    assert data[0]["train_data"][0]["second"] == 'quoted "value"'
    assert reads == ["fixtures/0.data"]


def test_inline_csv_quoted_header_delimiter_keeps_two_columns(
    monkeypatch,
    mlops_user,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b'"first,alias",second\nhealthy,ok\n',
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert list(data[0]["train_data"][0]) == ["first,alias", "second", "index"]
    assert reads == ["fixtures/0.data"]


def test_inline_csv_utf8_bom_keeps_quoted_header_contract(
    monkeypatch,
    mlops_user,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "2")
    serializer_class, instances = _instances("classification", "Classification", 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b'\xef\xbb\xbf"first,alias",second\nhealthy,ok\n',
    )

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert list(data[0]["train_data"][0]) == ["first,alias", "second", "index"]
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(("suffix", "basename"), CSV_SERIALIZER_CASES)
def test_inline_csv_rejects_total_cells_before_records_conversion(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
):
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS", "10")
    monkeypatch.setenv("MLOPS_INLINE_TRAIN_DATA_MAX_CSV_CELLS", "2")
    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(
        monkeypatch,
        instances,
        b"first,second\n1,2\n3,4\n",
    )

    with pytest.raises(serializers.ValidationError) as exc:
        serializer_class(
            instances,
            many=True,
            context={"request": _request(mlops_user)},
        ).data

    assert exc.value.detail["reason"] == "csv_cells"
    assert reads == ["fixtures/0.data"]


@pytest.mark.parametrize(("suffix", "basename"), CSV_SERIALIZER_CASES)
@pytest.mark.parametrize(
    "content",
    (
        b"",
        b'first,second\n1,"unterminated\n',
    ),
)
def test_inline_csv_parse_failures_keep_item_level_error_contract(
    monkeypatch,
    mlops_user,
    suffix,
    basename,
    content,
):
    serializer_class, instances = _instances(suffix, basename, 1)
    reads = _install_file_reader(monkeypatch, instances, content)

    data = serializer_class(
        instances,
        many=True,
        context={"request": _request(mlops_user)},
    ).data

    assert data[0]["train_data"] == []
    assert "error" in data[0]
    assert reads == ["fixtures/0.data"]
