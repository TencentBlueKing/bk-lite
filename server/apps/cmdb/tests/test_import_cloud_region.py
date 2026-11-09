"""主机和子网导入必须把云区域核对到节点管理清单，并写成云区域 ID。"""

import io

import openpyxl

from apps.cmdb.utils.Import import Import

REGIONS = [{"id": 1, "name": "default"}, {"id": 2, "name": "test"}]


def _regions(monkeypatch, rows=REGIONS, boom=False):
    calls = []

    class _NodeMgmt:
        def cloud_region_list(self):
            calls.append("cloud_region_list")
            if boom:
                raise RuntimeError("node down")
            return rows

    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", _NodeMgmt)
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.model_association_search", lambda *args, **kwargs: [])
    return calls


def _book(model_id, headers, keys, data_rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = model_id
    sheet.append(headers)
    sheet.append(["字符串"] * len(headers))
    sheet.append(keys)
    for row in data_rows:
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


def _host_attrs():
    return [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
        {"attr_id": "ip_addr", "attr_name": "内网IP", "attr_type": "str"},
        {"attr_id": "cloud", "attr_name": "云区域", "attr_type": "str", "is_required": True},
    ]


def test_match_cloud_region_prefers_id_then_name():
    assert Import.match_cloud_region(1, REGIONS) == 1
    assert Import.match_cloud_region(" 2 ", REGIONS) == 2
    assert Import.match_cloud_region("default", REGIONS) == 1
    assert Import.match_cloud_region(" test ", REGIONS) == 2
    assert Import.match_cloud_region("99999", REGIONS) is None
    assert Import.match_cloud_region("幽灵区域", REGIONS) is None
    assert Import.match_cloud_region(True, REGIONS) is None
    named_two = [{"id": 5, "name": "2"}]
    assert Import.match_cloud_region("2", named_two) == 5
    both = [{"id": 2, "name": "区二"}, {"id": 5, "name": "2"}]
    assert Import.match_cloud_region("2", both) == 2


def test_sync_import_keeps_known_cloud_and_drops_unknown(monkeypatch):
    calls = _regions(monkeypatch)
    importer = Import("host", _host_attrs(), [], "admin")
    rows, _asso = importer.format_excel_data(
        _book(
            "host",
            ["实例名", "内网IP", "云区域"],
            ["inst_name", "ip_addr", "cloud"],
            [
                ["by-id", "10.0.0.1", 1],
                ["by-name", "10.0.0.2", "default"],
                ["unknown-id", "10.0.0.3", "99999"],
                ["unknown-name", "10.0.0.4", "幽灵区域"],
            ],
        )
    )

    assert calls == ["cloud_region_list"]
    assert {row["inst_name"]: row["cloud"] for row in rows} == {"by-id": 1, "by-name": 1}
    assert all(isinstance(row["cloud"], int) for row in rows)
    assert any("99999" in message and "不在节点管理云区域中" in message for message in importer.validation_errors)
    assert any("幽灵区域" in message and "不在节点管理云区域中" in message for message in importer.validation_errors)


def test_transfer_import_reports_unknown_cloud_on_the_column(monkeypatch):
    _regions(monkeypatch)
    importer = Import("host", _host_attrs(), [], "admin")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "host"
    for row in (
        ["提示", "实例名", "内网IP", "云区域"],
        ["类型", "str", "str", "str"],
        ["字段标识(请勿编辑)", "inst_name", "ip_addr", "cloud"],
        [None, "ok", "10.0.0.1", "test"],
        [None, "bad", "10.0.0.2", "鲸眼"],
    ):
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)

    rows = list(importer.iter_transfer_rows(stream, [1]))

    assert rows[0][1]["cloud"] == 2
    assert rows[0][3] == []
    column, field_id, reason = rows[1][3][0]
    assert column == "D 云区域"
    assert field_id == "cloud"
    assert reason == "第5行，字段'云区域'的值'鲸眼'不在节点管理云区域中"


def test_subnet_import_checks_cloud_id(monkeypatch):
    _regions(monkeypatch)
    importer = Import(
        "subnet",
        [
            {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
            {"attr_id": "cloud_id", "attr_name": "云区域", "attr_type": "str"},
        ],
        [],
        "admin",
    )
    rows, _asso = importer.format_excel_data(
        _book(
            "subnet",
            ["实例名", "云区域"],
            ["inst_name", "cloud_id"],
            [["known", "test"], ["missing", "no-such"]],
        )
    )
    assert rows == [{"model_id": "subnet", "inst_name": "known", "cloud_id": 2}]
    assert "no-such" in importer.validation_errors[0]


def test_other_model_cloud_text_is_not_a_region(monkeypatch):
    calls = _regions(monkeypatch)
    importer = Import(
        "switch",
        [
            {"attr_id": "inst_name", "attr_name": "实例名", "attr_type": "str"},
            {"attr_id": "cloud", "attr_name": "云平台", "attr_type": "str"},
        ],
        [],
        "admin",
    )
    rows, _asso = importer.format_excel_data(
        _book(
            "switch",
            ["实例名", "云平台"],
            ["inst_name", "cloud"],
            [["sw", "幽灵区域"]],
        )
    )
    assert calls == []
    assert rows == [{"model_id": "switch", "inst_name": "sw", "cloud": "幽灵区域"}]
    assert importer.validation_errors == []


def test_cloud_region_outage_rejects_the_cell(monkeypatch):
    _regions(monkeypatch, boom=True)
    importer = Import("host", _host_attrs(), [], "admin")
    rows, _asso = importer.format_excel_data(
        _book(
            "host",
            ["实例名", "内网IP", "云区域"],
            ["inst_name", "ip_addr", "cloud"],
            [["a", "10.0.0.1", "default"], ["b", "10.0.0.2", 1]],
        )
    )
    assert rows == []
    assert importer.validation_errors == [
        "第4行，字段'云区域'暂时无法核对云区域",
        "第5行，字段'云区域'暂时无法核对云区域",
    ]
