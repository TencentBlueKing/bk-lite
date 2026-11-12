from typing import Any, Literal

from pydantic import BaseModel, Field

FIELD_TYPES = {
    "input",
    "number",
    "textarea",
    "richtext",
    "radio",
    "checkbox",
    "datetime",
    "select",
    "multiselect",
    "user",
    "group",
    "table",
    "cmdb",
    "attachment",
    "description",
    "divider",
    "date",
    "time",
    "dateRange",
    "cascade",
    "multiCascade",
    "multiUser",
    "userGroup",
    "multiUserGroup",
    "link",
    "calculate",
    "organization",
    "section",
    "tab",
    "task",
    "nestedTable",
    "subProcessForm",
    "multiCmdb",
    "cab",
    "associateConfig",
    "singleAssociateConfig",
    "signature",
}

LAYOUT_ONLY = {"description", "divider", "section", "tab"}


class FieldSchema(BaseModel):
    key: str
    type: str
    label: str = ""
    required: bool = False
    default: Any = None
    placeholder: str = ""
    props: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] | None = None
    columns: list[dict[str, Any]] = Field(default_factory=list)
    span: int | None = None
    group: str = ""
    visibleWhen: dict[str, Any] | None = None
    state: str = "default"
    hideValueClearMode: str = "keep"
    hideLogic: str = "visible"
    children: list["FieldSchema"] = Field(default_factory=list)


FieldSchema.model_rebuild()


class RuleSchema(BaseModel):
    type: Literal["visible", "required", "compute"]
    field: str
    when: dict[str, Any] | None = None
    expr: str | None = None


class FormSchemaModel(BaseModel):
    version: int = 1
    fields: list[FieldSchema]
    layout: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[RuleSchema] = Field(default_factory=list)

    def field_map(self) -> dict[str, FieldSchema]:
        return {field.key: field for field in self.fields}
