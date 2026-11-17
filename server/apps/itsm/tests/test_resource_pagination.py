import json

import pytest

from apps.itsm.models.extend import BizObject
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import resources

pytestmark = pytest.mark.django_db


def test_resource_pagination_does_not_truncate_at_one_hundred():
    BizObject.objects.bulk_create([BizObject(name=f"对象{i}", key=f"obj{i}") for i in range(105)])
    BizObject.objects.create(name="其他域", key="outside", domain="other")
    first = json.loads(resources(request(payload={"page": 1, "page_size": 100}, permissions=["biz_object-View"]), "biz_objects").content)["data"]
    second = json.loads(resources(request(payload={"page": 2, "page_size": 100}, permissions=["biz_object-View"]), "biz_objects").content)["data"]
    assert first["count"] == second["count"] == 105
    assert len(first["items"]) == 100
    assert len(second["items"]) == 5
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})


def test_resource_pagination_keeps_permission_check():
    assert resources(request(payload={"page": 2}), "biz_objects").status_code == 403
