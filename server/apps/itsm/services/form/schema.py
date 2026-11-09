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
}

LAYOUT_ONLY = {"description", "divider"}


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
