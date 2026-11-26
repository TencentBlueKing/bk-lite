from django.conf import settings

from apps.itsm.flowable.client import FlowableClient, FlowableError


def deploy_table(table) -> dict:
    """把本地决策表部署到 Flowable DMN。规则为空时不部署。"""
    rules = []
    raw = table.rules or []
    rows = raw.get("rows") if isinstance(raw, dict) else raw
    for rule in rows or []:
        if isinstance(raw, dict):
            conditions = rule.get("conditions") or {}
            results = rule.get("results") or {}
            raw_value = next(iter(conditions.values()), "")
            value = str(raw_value.get("value") if isinstance(raw_value, dict) else raw_value).replace('"', "")
            output = str(next(iter(results.values()), "")).replace('"', "")
        else:
            when = rule.get("when") or {}
            then = rule.get("then") or {}
            value = str(when.get("value") or "").replace('"', "")
            output = str(next(iter(then.values()), "")) if isinstance(then, dict) and then else ""
            output = output.replace('"', "")
        if not value:
            continue
        rules.append(f'<rule><inputEntry><text>"{value}"</text></inputEntry><outputEntry><text>"{output}"</text></outputEntry></rule>')
    if not rules or not settings.FLOWABLE_PASSWORD:
        return {"deployed": False}
    xml = (
        '<definitions xmlns="http://www.omg.org/spec/DMN/20180521/MODEL/" '
        f'id="itsm_decision_{table.id}" name="{table.name}" namespace="http://bk-lite/itsm">'
        f'<decision id="decision_{table.id}" name="{table.name}">'
        '<decisionTable id="table" hitPolicy="FIRST">'
        '<input id="input_value"><inputExpression typeRef="string"><text>value</text></inputExpression></input>'
        '<output id="output_value" name="result" typeRef="string"/>'
        f'{"".join(rules)}'
        "</decisionTable></decision></definitions>"
    )
    try:
        deployed = FlowableClient(settings.FLOWABLE_URL, settings.FLOWABLE_USER, settings.FLOWABLE_PASSWORD).deploy_dmn(
            f"itsm_decision_{table.id}", xml
        )
    except FlowableError as exc:
        return {"deployed": False, "status": exc.status}
    return {"deployed": True, "id": deployed.get("id")}
