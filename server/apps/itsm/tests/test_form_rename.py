import json

import pytest
from django.urls import resolve

from apps.itsm.models import FormModel, FormVersion
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import form_detail, forms


@pytest.mark.django_db
def test_form_name_edit_is_scoped_and_preserves_schema_and_version():
    form = FormModel.objects.create(key="expense", name="旧名称")
    version = FormVersion.objects.create(form=form, version_no=1, schema={"fields": [{"key": "amount"}]}, is_published=True)
    form.current_version = version
    form.save()
    rename = resolve(f"/api/v1/itsm/api/forms/{form.id}/name/").func
    for permission in ("form-Edit", "form-View"):
        detail = form_detail(request(permissions=[permission, "form-View"]), form.id)
        assert json.loads(detail.content)["data"]["can_edit"] == (permission == "form-Edit")
    for value in ("  ", "字" * 129, 123):
        assert rename(request("put", {"name": value}, permissions=["form-Edit"]), form.id).status_code == 400
    payload = {"name": " 费用报销 "}
    assert rename(request("put", payload, permissions=["form-View"]), form.id).status_code == 403
    assert rename(request("put", payload, permissions=["form-Edit"], domain="other"), form.id).status_code == 404
    assert rename(request("put", payload, permissions=["form-Edit"]), form.id).status_code == 200
    form.refresh_from_db()
    assert (form.key, form.name, form.current_version_id) == ("expense", "费用报销", version.id)
    assert form.versions.get().schema == {"fields": [{"key": "amount"}]}
    assert json.loads(forms(request(permissions=["form-View"])).content)["data"]["items"][0]["name"] == "费用报销"
