from typing import Any

from pydantic import BaseModel, Field

PHASE1_TYPES = {
    "start",
    "submit",
    "approval",
    "handle",
    "manual",
    "cc",
    "notice",
    "exclusive",
    "branch",
    "branch_condition",
    "parallel",
    "parallel_condition",
    "converge",
    "end",
    "auto",
    "decision",
    "call",
    "subprocess",
    "subprocess_submit",
    "subprocess_handle",
    "manual_trigger",
    "rule_trigger",
    "auto_dispatch",
    "knowledge",
}


class DesignNode(BaseModel):
    id: str
    type: str
    name: str = ""
    assignee: dict[str, Any] | None = None
    multi: dict[str, Any] | None = None
    fallback: str | None = None
    field_perm: dict[str, str] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)
    auto: dict[str, Any] | None = None


class DesignEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    condition: dict[str, Any] | None = None
    default: bool = False

    model_config = {"populate_by_name": True}


class DesignDocument(BaseModel):
    nodes: list[DesignNode]
    edges: list[DesignEdge]
    settings: dict[str, Any] = Field(default_factory=dict)

    def node_map(self) -> dict[str, DesignNode]:
        return {node.id: node for node in self.nodes}
