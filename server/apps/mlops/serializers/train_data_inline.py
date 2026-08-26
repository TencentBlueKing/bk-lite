"""CSV/TXT TrainData 列表内联读取的统一资源边界。"""

import os
from io import BytesIO

from rest_framework import serializers

MAX_INLINE_LIST_ITEMS = 20
MAX_INLINE_FILE_BYTES = 4 * 1024 * 1024
MAX_INLINE_TOTAL_BYTES = 8 * 1024 * 1024
MAX_INLINE_RECORDS = 50_000
MAX_INLINE_CSV_COLUMNS = 256
MAX_INLINE_CSV_CELLS = 500_000


def _configured_limit(name, hard_limit):
    """读取只能下调的资源额度，非法配置回退到安全硬上限。"""
    try:
        value = int(os.getenv(name, str(hard_limit)))
    except (TypeError, ValueError):
        return hard_limit
    if value <= 0:
        return hard_limit
    return min(value, hard_limit)


class InlineTrainDataLimitExceeded(serializers.ValidationError):
    """列表内联读取超过稳定资源契约。"""

    def __init__(self, reason, limit):
        super().__init__(
            {
                "error": "inline_train_data_limit_exceeded",
                "reason": reason,
                "limit": limit,
            },
            code="inline_train_data_limit_exceeded",
        )


class _InlineTrainDataBudget:
    def __init__(self):
        self.max_list_items = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_LIST_ITEMS",
            MAX_INLINE_LIST_ITEMS,
        )
        self.max_file_bytes = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_FILE_BYTES",
            MAX_INLINE_FILE_BYTES,
        )
        self.max_total_bytes = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_TOTAL_BYTES",
            MAX_INLINE_TOTAL_BYTES,
        )
        self.max_records = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_RECORDS",
            MAX_INLINE_RECORDS,
        )
        self.max_csv_columns = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_CSV_COLUMNS",
            MAX_INLINE_CSV_COLUMNS,
        )
        self.max_csv_cells = _configured_limit(
            "MLOPS_INLINE_TRAIN_DATA_MAX_CSV_CELLS",
            MAX_INLINE_CSV_CELLS,
        )
        self.used_bytes = 0
        self.used_records = 0
        self.used_csv_cells = 0
        self.used_files = 0

    def read(self, field_file):
        if self.used_files >= self.max_list_items:
            raise InlineTrainDataLimitExceeded("list_items", self.max_list_items)
        self.used_files += 1
        remaining_total_bytes = self.max_total_bytes - self.used_bytes
        read_limit = min(self.max_file_bytes, remaining_total_bytes)
        with field_file.storage.open(field_file.name, "rb") as stream:
            content = _read_until_eof_or_limit(
                stream,
                read_limit + 1,
                on_chunk=self._consume_transferred_bytes,
            )
        if len(content) > read_limit:
            if self.max_file_bytes <= remaining_total_bytes:
                raise InlineTrainDataLimitExceeded(
                    "file_bytes",
                    self.max_file_bytes,
                )
            raise InlineTrainDataLimitExceeded("total_bytes", self.max_total_bytes)
        return content

    def _consume_transferred_bytes(self, count):
        self.used_bytes += count

    @property
    def remaining_records(self):
        return self.max_records - self.used_records

    @property
    def remaining_csv_cells(self):
        return self.max_csv_cells - self.used_csv_cells

    def consume_records(self, count, csv_columns=None, csv_cells=None):
        if csv_columns is not None and csv_columns > self.max_csv_columns:
            raise InlineTrainDataLimitExceeded("csv_columns", self.max_csv_columns)
        if count > self.remaining_records:
            raise InlineTrainDataLimitExceeded("records", self.max_records)
        output_cells = count * csv_columns if csv_columns is not None else 0
        charged_csv_cells = max(csv_cells or 0, output_cells)
        if charged_csv_cells > self.remaining_csv_cells:
            raise InlineTrainDataLimitExceeded("csv_cells", self.max_csv_cells)
        self.used_records += count
        self.used_csv_cells += charged_csv_cells


def _read_until_eof_or_limit(stream, limit, on_chunk=None):
    content = bytearray()
    remaining = limit
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        if on_chunk is not None:
            on_chunk(len(chunk))
        content.extend(chunk)
        remaining -= len(chunk)
    return bytes(content)


def _scan_csv_shape(stream):
    stream.seek(0)
    content = stream.getbuffer()
    stream.seek(0)
    if not content:
        return 1, 1, 0, 0

    index = 0
    if len(content) >= 3 and tuple(content[:3]) == (0xEF, 0xBB, 0xBF):
        index = 3
    header_columns = None
    max_fields = 1
    data_records = 0
    data_fields = 0
    fields = 1
    in_quotes = False
    at_field_start = True
    record_nonblank = False

    def finish_record():
        nonlocal header_columns, max_fields, data_records, data_fields
        if not record_nonblank:
            return
        if header_columns is None:
            header_columns = fields
        else:
            data_records += 1
            data_fields += fields
        max_fields = max(max_fields, fields)

    while index < len(content):
        value = content[index]
        if in_quotes and value == ord('"'):
            if index + 1 < len(content) and content[index + 1] == ord('"'):
                index += 1
            else:
                in_quotes = False
        elif at_field_start and value == ord('"'):
            in_quotes = True
            at_field_start = False
            record_nonblank = True
        elif value == ord(",") and not in_quotes:
            fields += 1
            at_field_start = True
            record_nonblank = True
        elif value in (ord("\r"), ord("\n")) and not in_quotes:
            finish_record()
            fields = 1
            at_field_start = True
            record_nonblank = False
            if value == ord("\r") and index + 1 < len(content) and content[index + 1] == ord("\n"):
                index += 1
        else:
            at_field_start = False
            if value not in (ord(" "), ord("\t")):
                record_nonblank = True
        index += 1
    finish_record()
    if header_columns is None:
        return 1, 1, 0, 0
    return header_columns, max_fields, data_records, data_fields


def _prepare_collection(data):
    if hasattr(data, "filter") and hasattr(data, "exclude"):
        file_count = data.filter(train_data__isnull=False).exclude(train_data="").count()
        return data, file_count
    if not hasattr(data, "__len__"):
        data = list(data)
    return data, sum(bool(getattr(item, "train_data", None)) for item in data)


class BoundedInlineTrainDataListSerializer(serializers.ListSerializer):
    """仅为显式请求内联文件的列表设置固定最坏成本。"""

    def to_representation(self, data):
        if not self.child.include_train_data:
            return super().to_representation(data)

        data, file_count = _prepare_collection(data)
        budget = _InlineTrainDataBudget()
        if file_count > budget.max_list_items:
            raise InlineTrainDataLimitExceeded("list_items", budget.max_list_items)

        self.child._inline_train_data_budget = budget
        try:
            return super().to_representation(data)
        finally:
            del self.child._inline_train_data_budget


def open_inline_train_data(field_file, serializer):
    """列表走有界内存流；详情保持既有直读行为。"""
    budget = getattr(serializer, "_inline_train_data_budget", None)
    if budget is None:
        return field_file.open("rb")
    return BytesIO(budget.read(field_file))


def read_inline_train_data(field_file, serializer):
    """列表走有界字节读取；详情保持既有 FieldFile.read 行为。"""
    budget = getattr(serializer, "_inline_train_data_budget", None)
    if budget is None:
        return field_file.read()
    return budget.read(field_file)


def inline_csv_read_options(serializer, stream):
    """列表只让 Pandas 物化剩余额度加一行，以便可靠检测超限。"""
    budget = getattr(serializer, "_inline_train_data_budget", None)
    if budget is None:
        return {}, None
    csv_columns, max_fields, data_records, data_fields = _scan_csv_shape(stream)
    if csv_columns > budget.max_csv_columns or max_fields > budget.max_csv_columns:
        raise InlineTrainDataLimitExceeded("csv_columns", budget.max_csv_columns)
    if data_records > budget.remaining_records:
        raise InlineTrainDataLimitExceeded("records", budget.max_records)
    parser_cells = max(data_fields, data_records * csv_columns)
    if parser_cells > budget.remaining_csv_cells:
        raise InlineTrainDataLimitExceeded("csv_cells", budget.max_csv_cells)
    rows_by_cells = budget.remaining_csv_cells // csv_columns
    return {"nrows": min(budget.remaining_records, rows_by_cells) + 1}, parser_cells


def consume_inline_records(serializer, count, csv_columns=None, csv_cells=None):
    """在构造 Python records 前占用请求级对象额度。"""
    budget = getattr(serializer, "_inline_train_data_budget", None)
    if budget is not None:
        budget.consume_records(
            count,
            csv_columns=csv_columns,
            csv_cells=csv_cells,
        )
