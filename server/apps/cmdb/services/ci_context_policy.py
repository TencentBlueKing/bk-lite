from dataclasses import dataclass

CONTEXT_APPLICATION = "application"
LINK_FOLLOW = "follow"
LINK_INCLUDE = "include"
LINK_EXCLUDE = "exclude"
APPLICATION_MODEL = "application"
SYSTEM_MODEL = "system"
LAYER1_ASST = frozenset({"run", "connect"})
LAYER2_ASST = frozenset({"run"})
DENYLIST = frozenset({
    "switch", "router", "firewall", "loadbalance", "security_device",
    "rack", "physcial_server", "nic", "interface",
    "k8s_cluster", "k8s_namespace", "k8s_node", "k8s_pod",
})


@dataclass(frozen=True)
class ContextDecision:
    include: bool
    context: str = CONTEXT_APPLICATION
    layer: int | None = None
    root_uuid: str | None = None
    ci_uuid: str | None = None
    via_uuid: str | None = None
    attach_system_uuid: str | None = None
    model_asst_id: str = ""


def normalize_context_link(value) -> str:
    text = str(value or "").strip() or LINK_FOLLOW
    return text if text in {LINK_FOLLOW, LINK_INCLUDE, LINK_EXCLUDE} else LINK_FOLLOW


def classify_application_edge(edge: dict, *, src_is_member: bool) -> ContextDecision:
    src, dst = edge.get("src") or {}, edge.get("dst") or {}
    asst_id = str(edge.get("asst_id") or "").strip()
    model_asst_id = str(edge.get("model_asst_id") or "")
    link = normalize_context_link(edge.get("context_link"))
    src_model, dst_model = str(src.get("model_id") or ""), str(dst.get("model_id") or "")
    src_uuid, dst_uuid = str(src.get("inst_uuid") or ""), str(dst.get("inst_uuid") or "")

    if asst_id == "contains" and src_model == SYSTEM_MODEL and dst_model == APPLICATION_MODEL:
        return ContextDecision(include=False, attach_system_uuid=src_uuid, root_uuid=dst_uuid, model_asst_id=model_asst_id)

    layer1 = src_model == APPLICATION_MODEL and asst_id in LAYER1_ASST
    layer2 = src_is_member and asst_id in LAYER2_ASST and src_model != APPLICATION_MODEL
    include = layer1 or layer2
    if link == LINK_EXCLUDE:
        include = False
    elif link == LINK_INCLUDE:
        include = True
        if not layer1 and not layer2:
            layer1 = src_model == APPLICATION_MODEL
            layer2 = src_is_member and not layer1
    if include and dst_model in DENYLIST and link != LINK_INCLUDE:
        include = False
    if not include:
        return ContextDecision(include=False, model_asst_id=model_asst_id)
    if layer1 or (link == LINK_INCLUDE and src_model == APPLICATION_MODEL):
        return ContextDecision(include=True, layer=1, root_uuid=src_uuid, ci_uuid=dst_uuid, model_asst_id=model_asst_id)
    return ContextDecision(include=True, layer=2, ci_uuid=dst_uuid, via_uuid=src_uuid, model_asst_id=model_asst_id)
