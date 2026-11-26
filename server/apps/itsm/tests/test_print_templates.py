import json
import re

import pytest

from apps.itsm.models.extend import PrintTemplate
from apps.itsm.tests import test_review_regressions
from apps.itsm.views.extend import resource_item, resources
from apps.itsm.views.ticket_operations import preview_print_template, render_print

pytestmark = pytest.mark.django_db
request = test_review_regressions.request
sample = test_review_regressions.sample

PRINT_PERMISSIONS = ["print-View", "print-Add", "print-Edit", "print-Delete"]


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_print_templates_validate_and_respect_action_permissions():
    payload = {"name": "审批凭证", "body": "<h1>{{ title }}</h1><p>{{ sn }} · {{ creator }}</p>"}
    listing = data(resources(request(permissions=["print-View"]), "prints"))
    assert [listing[key] for key in ("can_add", "can_edit", "can_delete")] == [False, False, False]
    assert resources(request("post", payload, permissions=["print-View"]), "prints").status_code == 403

    for invalid in ({**payload, "name": " "}, {**payload, "body": 1}, {**payload, "body": "{{ title "}, {**payload, "body": "{{ secret }}"}):
        assert resources(request("post", invalid, permissions=PRINT_PERMISSIONS), "prints").status_code == 400
    assert not PrintTemplate.objects.exists()

    created = data(resources(request("post", payload, permissions=PRINT_PERMISSIONS), "prints"))
    edited = data(resource_item(request("patch", {"name": "  工单凭证  "}, permissions=PRINT_PERMISSIONS), "prints", created["id"]))
    assert edited["name"] == "工单凭证"
    assert (
        resource_item(request("patch", {"body": "{{ title.__class__ }}"}, permissions=PRINT_PERMISSIONS), "prints", created["id"]).status_code == 400
    )
    assert PrintTemplate.objects.get(id=created["id"]).body == payload["body"]
    assert resource_item(request("delete", permissions=PRINT_PERMISSIONS, domain="elsewhere.test"), "prints", created["id"]).status_code == 404
    assert data(resource_item(request("delete", permissions=PRINT_PERMISSIONS), "prints", created["id"])) == {"id": created["id"]}


def test_ticket_print_uses_one_layout_independent_of_saved_templates(sample):
    ticket, _ = sample
    custom = PrintTemplate.objects.create(name="自定义版式", body="<p>仅自定义模板</p>")
    external = PrintTemplate.objects.create(name="其他客户", body="{{ creator }}", domain="elsewhere.test")

    result = data(render_print(request(username="owner", permissions=["ticket-View"]), ticket.id))
    assert set(result) == {"html"}
    assert "<h1>申请</h1>" in result["html"]
    assert ticket.sn in result["html"]
    assert '<th scope="row">amount</th><td>100</td>' in result["html"]
    assert "仅自定义模板" not in result["html"]
    for params in ({"template_id": custom.id}, {"template_id": external.id}, {"include_templates": "1"}):
        assert data(render_print(request(payload=params, username="owner"), ticket.id)) == result
    assert PrintTemplate.objects.filter(id__in=[custom.id, external.id]).count() == 2
    assert render_print(request(username="outsider"), ticket.id).status_code == 404
    assert render_print(request(username="owner", domain="elsewhere.test"), ticket.id).status_code == 404
    assert render_print(request(username="owner", permissions=["print-View"]), ticket.id).status_code == 403


def test_print_example_has_same_sections_as_ticket_print(sample):
    ticket, _ = sample
    assert preview_print_template(request("post", {})).status_code == 403
    example = data(preview_print_template(request("post", {}, permissions=["print-View"])))["html"]
    document = data(render_print(request(username="owner"), ticket.id))["html"]
    section_tags = r"<(?:h[12]|table)(?: [^>]+)?>"
    assert re.findall(section_tags, example) == re.findall(section_tags, document)
    assert re.findall(section_tags, example).count('<table class="itsm-print-fields">') == 2
    assert "<h1>示例工单</h1>" in example
    assert "<h2>表单字段</h2>" in example
    assert ticket.sn not in example
    assert "original" not in example
    assert data(preview_print_template(request("post", {"body": "<p>自定义样例</p>"}, permissions=["print-View"])))["html"] == example


def test_print_renders_all_fields_using_ticket_visibility(sample):
    ticket, _ = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["field_perm"]["secret"] = "hidden"
    version.design["form_schema"] = {
        "fields": [
            {"key": "amount", "label": "申请金额", "type": "number"},
            {"key": "secret", "label": "审批专用", "type": "input"},
            {
                "key": "choice",
                "label": "<分组>",
                "type": "select",
                "source": {"type": "static", "options": [{"value": "one", "label": "第一级"}]},
            },
            {"key": "details", "label": "说明", "type": "input"},
            {"key": "empty_details", "label": "补充说明", "type": "input"},
            {
                "key": "conditional",
                "label": "条件字段",
                "type": "input",
                "visibleWhen": {"logic": "and", "items": [{"field": "choice", "op": "=", "value": "two"}]},
            },
            {
                "key": "partly_hidden",
                "label": "组合条件字段",
                "type": "input",
                "visibleWhen": {
                    "logic": "or",
                    "items": [{"field": "choice", "op": "=", "value": "one"}, {"field": "amount", "op": "=", "value": 200}],
                },
            },
            {
                "key": "items",
                "type": "input",
                "state": "hidden",
            },
            {"key": "container", "type": "section", "state": "hidden", "children": [{"key": "nested", "type": "input"}]},
            {
                "key": "order",
                "label": "子表",
                "type": "table",
                "children": [
                    {"key": "name", "label": "采购品名", "type": "input"},
                    {"key": "quantity", "label": "敏感库存", "type": "number", "state": "hidden"},
                ],
            },
            {"key": "rule_hidden", "type": "input"},
        ],
        "rules": [{"type": "visible", "field": "rule_hidden", "when": {"field": "choice", "op": "=", "value": "two"}}],
    }
    version.save(update_fields=["design"])
    ticket.form_data.update(
        choice="one",
        details="<内容>",
        conditional="仅特定场景可见",
        partly_hidden="部分命中仍隐藏",
        items="隐藏的同名字段",
        nested="隐藏分组内",
        _field_receipts="内部字段",
        order=[{"name": "服务器", "quantity": 98765}],
        rule_hidden="显隐规则保护值",
    )
    ticket.save(update_fields=["form_data"])
    handler = data(render_print(request(username="handler"), ticket.id))["html"]
    assert '<th scope="row">申请金额</th><td>100</td>' in handler
    assert '<th scope="row">&lt;分组&gt;</th><td>第一级</td>' in handler
    assert '<th scope="row">补充说明</th><td>—</td>' in handler
    assert "&lt;分组&gt;" in handler
    assert "&lt;内容&gt;" in handler
    assert "采购品名：服务器" in handler
    for restricted in ("original", "审批专用", "仅特定场景可见", "隐藏分组内", "内部字段", "部分命中仍隐藏", "隐藏的同名字段", "显隐规则保护值", "98765"):
        assert restricted not in handler
    owner = data(render_print(request(username="owner"), ticket.id))["html"]
    assert '<th scope="row">审批专用</th><td>original</td>' in owner
    ticket.form_data["choice"] = "two"
    ticket.save(update_fields=["form_data"])
    visible = data(render_print(request(username="handler"), ticket.id))["html"]
    assert "仅特定场景可见" in visible
    assert "显隐规则保护值" in visible


def test_stored_custom_template_keeps_existing_ast_validation():
    def save(body):
        return resources(request("post", {"name": "旧版式", "body": body}, permissions=PRINT_PERMISSIONS), "prints")

    body = '<h1>{{ status }}</h1><p>{{ form["amount"] }}</p>{{ form_fields }}'
    assert data(save(body))["body"] == body
    for body in ("{{ form }}", "{{ form[title] }}", '{{ title["name"] }}', '{{ form["a"]["b"] }}', "{{ form.values() }}"):
        assert save(body).status_code == 400
