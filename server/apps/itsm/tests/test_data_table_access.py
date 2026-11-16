import json

import pytest

from apps.itsm.models import DataTable, DataTableRow
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.m2 import data_table_rows

pytestmark = pytest.mark.django_db


def test_view_permission_reads_rows_but_cannot_write():
    table = DataTable.objects.create(name="设备", key="assets")
    DataTableRow.objects.create(table=table, data={"name": "设备一"})
    response = data_table_rows(request(permissions=["data-View"]), table.id)
    assert response.status_code == 200
    data = json.loads(response.content)["data"]
    assert data["items"][0]["data"]["name"] == "设备一"
    assert data["can_edit"] is False
    assert data_table_rows(request("post", {"data": {"name": "bad"}}, permissions=["data-View"]), table.id).status_code == 403


def test_data_rows_reject_cross_domain_and_unsupported_method():
    table = DataTable.objects.create(name="设备", key="assets")
    assert data_table_rows(request(domain="other", permissions=["data-View"]), table.id).status_code == 404
    assert data_table_rows(request("delete", permissions=["data-Edit"]), table.id).status_code == 405
