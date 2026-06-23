from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


MaskStrategy = Literal["full", "last4"]
FieldType = Literal["string", "password", "number", "boolean", "select", "textarea"]
InputMode = Literal["department_select", "manual_input"]


class TemplateFieldManifest(BaseModel):
    key: str = Field(description="字段唯一键")
    label: str = Field(description="字段展示名称")
    field_type: FieldType = Field(default="string", description="字段类型")
    required: bool = Field(default=False, description="是否必填")
    secret: bool = Field(default=False, description="是否为敏感字段")
    write_only: bool = Field(default=False, description="是否仅写入不回显")
    mask_strategy: MaskStrategy = Field(default="full", description="敏感字段回显脱敏策略")
    default: Any = Field(default=None, description="默认值")
    placeholder: str = Field(default="", description="占位提示")
    help_text: str = Field(default="", description="帮助文案")
    options: list[dict[str, Any]] = Field(default_factory=list, description="选择型字段可选项")
    reset_capabilities: list[str] = Field(default_factory=list, description="字段变更后需要回退的 capability 列表")
    input_mode: InputMode | None = Field(default=None, description="范围字段输入模式")

    @model_validator(mode="after")
    def validate_secret_flags(self):
        if self.secret:
            self.write_only = True
        return self


class TemplateGroupManifest(BaseModel):
    key: str = Field(description="分组唯一键")
    title: str = Field(description="分组展示名称")
    description: str = Field(default="", description="分组描述")
    fields: list[TemplateFieldManifest] = Field(default_factory=list, description="分组字段列表")


class BusinessTemplateManifest(BaseModel):
    """业务模板：描述一组带分组结构的表单字段，支持外部字段映射声明。"""

    title: str = Field(description="模板展示名称")
    groups: list[TemplateGroupManifest] = Field(default_factory=list, description="字段分组列表")
    available_external_fields: list[str] = Field(default_factory=list, description="可映射的外部字段列表")
    matchable_fields: list[str] = Field(default_factory=list, description="允许用于匹配的外部字段列表")
    receivable_fields: list[str] = Field(default_factory=list, description="允许用于发送接收标识的外部字段列表")
    identity_fields: list[str] = Field(default_factory=list, description="可作为外部稳定身份的字段列表")
    default_external_match_field: str = Field(default="", description="默认外部匹配字段")
    default_external_receive_field: str = Field(default="", description="默认外部接收字段")

    @model_validator(mode="after")
    def validate_unique_field_keys(self):
        seen: set[str] = set()
        for group in self.groups:
            for field in group.fields:
                if field.key in seen:
                    raise ValueError(
                        f"Duplicate field key '{field.key}' found across groups in business template '{self.title}'"
                    )
                seen.add(field.key)
        return self


class CapabilityManifest(BaseModel):
    key: str = Field(description="capability 唯一键")
    name: str = Field(description="capability 展示名称")
    description: str = Field(default="", description="capability 描述")
    adapter_key: str = Field(description="adapter 注册键")
    adapter_path: str = Field(description="adapter 类导入路径")
    connection_template: list[TemplateFieldManifest] = Field(default_factory=list, description="实例级 capability 接口配置模板")
    business_template: str = Field(default="", description="业务配置模板键，引用 ProviderManifest.business_templates 中的条目")


class ProviderManifest(BaseModel):
    key: str = Field(description="provider 唯一键")
    name: str = Field(description="provider 展示名称")
    description: str = Field(default="", description="provider 描述")
    instance_templates: dict[str, BusinessTemplateManifest] = Field(
        default_factory=dict,
        description="实例连接模板字典，key 为模板名称（如 base_connection）",
    )
    business_templates: dict[str, BusinessTemplateManifest] = Field(
        default_factory=dict,
        description="业务配置模板字典，key 为模板名称，capability.business_template 引用此处的 key",
    )
    capabilities: list[CapabilityManifest] = Field(default_factory=list, description="provider 支持的 capabilities")

    @property
    def instance_template(self) -> list[TemplateFieldManifest]:
        """将所有 instance_templates 分组字段展平，便于后向兼容调用。"""
        fields: list[TemplateFieldManifest] = []
        for template in self.instance_templates.values():
            for group in template.groups:
                fields.extend(group.fields)
        return fields

    @model_validator(mode="after")
    def validate_unique_keys(self):
        capability_keys = [item.key for item in self.capabilities]
        if len(capability_keys) != len(set(capability_keys)):
            raise ValueError(f"Duplicate capability keys found in provider '{self.key}'")

        valid_capabilities = set(capability_keys)
        all_field_keys: set[str] = set()
        for field in self.get_all_connection_fields():
            if field.key in all_field_keys:
                raise ValueError(f"Duplicate config field keys found in provider '{self.key}': {field.key}")
            all_field_keys.add(field.key)
            invalid_capabilities = set(field.reset_capabilities) - valid_capabilities
            if invalid_capabilities:
                raise ValueError(
                    f"Field '{field.key}' in provider '{self.key}' references unknown capabilities: {sorted(invalid_capabilities)}"
                )

        for capability in self.capabilities:
            if capability.business_template and capability.business_template not in self.business_templates:
                raise ValueError(
                    f"Capability '{capability.key}' in provider '{self.key}' references unknown business_template: '{capability.business_template}'"
                )
        return self

    def get_capability(self, capability_key: str) -> CapabilityManifest | None:
        for capability in self.capabilities:
            if capability.key == capability_key:
                return capability
        return None

    def get_instance_field(self, field_key: str) -> TemplateFieldManifest | None:
        for field in self.instance_template:
            if field.key == field_key:
                return field
        return None

    def get_capability_connection_fields(self, capability_key: str) -> list[TemplateFieldManifest]:
        capability = self.get_capability(capability_key)
        if capability is None:
            return []
        return list(capability.connection_template)

    def get_all_connection_fields(self) -> list[TemplateFieldManifest]:
        fields = list(self.instance_template)
        for capability in self.capabilities:
            fields.extend(capability.connection_template)
        return fields

    def get_scoped_connection_fields(self, config_scope: str = "") -> list[TemplateFieldManifest]:
        if not config_scope:
            return self.get_all_connection_fields()
        if config_scope == "base":
            return list(self.instance_template)
        return list(self.instance_template) + self.get_capability_connection_fields(config_scope)

    def get_secret_fields(self) -> list[TemplateFieldManifest]:
        return [field for field in self.get_all_connection_fields() if field.secret or field.write_only]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            # 展平列表保持向后兼容（detail page 的基础连接 tab 使用）
            "instance_template": [field.model_dump() for field in self.instance_template],
            "instance_templates": {k: v.model_dump() for k, v in self.instance_templates.items()},
            "business_templates": {k: v.model_dump() for k, v in self.business_templates.items()},
            "capabilities": [
                {
                    "key": capability.key,
                    "name": capability.name,
                    "description": capability.description,
                    "connection_template": [field.model_dump() for field in capability.connection_template],
                    "business_template": capability.business_template,
                }
                for capability in self.capabilities
            ],
        }
