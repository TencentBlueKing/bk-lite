import json

import pytest

from apps.itsm.models import DataDictionary, DataDictionaryItem
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import dictionary_items

pytestmark = pytest.mark.django_db


def test_read_only_can_view_but_not_edit():
    dictionary = DataDictionary.objects.create(key="dict", name="字典")
    item = DataDictionaryItem.objects.create(dictionary=dictionary, key="a", label="甲")
    response = dictionary_items(request(permissions=["data-View"]), dictionary.id)
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["can_edit"] is False
    assert dictionary_items(request("post", {"id": item.id, "label": "乙"}, permissions=["data-View"]), dictionary.id).status_code == 403


def test_edit_preserves_identity_and_parent():
    dictionary = DataDictionary.objects.create(key="dict", name="字典")
    parent = DataDictionaryItem.objects.create(dictionary=dictionary, key="p", label="父")
    item = DataDictionaryItem.objects.create(dictionary=dictionary, key="a", label="甲", parent=parent)
    response = dictionary_items(
        request("post", {"id": item.id, "key": "changed", "label": "乙", "order": 2, "is_enabled": False}, permissions=["data-Edit"]),
        dictionary.id,
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert (item.key, item.label, item.order, item.is_enabled, item.parent_id) == ("a", "乙", 2, False, parent.id)


@pytest.mark.parametrize(
    "payload", [{"key": "a", "label": ""}, {"key": "a", "label": "甲", "order": -1}, {"key": "a", "label": "甲", "is_enabled": "false"}]
)
def test_invalid_entry_rejected(payload):
    dictionary = DataDictionary.objects.create(key="dict", name="字典")
    response = dictionary_items(request("post", payload, permissions=["data-Edit"]), dictionary.id)
    assert response.status_code == 400
    assert not dictionary.items.exists()


def test_edit_cannot_cross_dictionary_or_domain():
    a = DataDictionary.objects.create(key="a", name="甲")
    b = DataDictionary.objects.create(key="b", name="乙")
    item = DataDictionaryItem.objects.create(dictionary=b, key="a", label="甲")
    assert dictionary_items(request("post", {"id": item.id, "label": "乙"}, permissions=["data-Edit"]), a.id).status_code == 404
    assert dictionary_items(request(domain="other", permissions=["data-View"]), a.id).status_code == 404


def test_delete_leaf_and_protect_parent():
    dictionary = DataDictionary.objects.create(key="dict", name="字典")
    parent = DataDictionaryItem.objects.create(dictionary=dictionary, key="p", label="父")
    child = DataDictionaryItem.objects.create(dictionary=dictionary, key="c", label="子", parent=parent)
    req = request("delete", permissions=["data-Edit"])
    req.GET = {"id": str(parent.id)}
    assert dictionary_items(req, dictionary.id).status_code == 400
    req.GET = {"id": str(child.id)}
    assert dictionary_items(req, dictionary.id).status_code == 200
    assert dictionary.items.count() == 1
