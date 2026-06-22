export type InstanceStatus = 'pending_verification' | 'ready' | 'verification_failed';

export interface TemplateField {
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  secret: boolean;
  write_only: boolean;
  mask_strategy: string;
  default: unknown;
  placeholder: string;
  help_text: string;
  options: Array<{ value: unknown; label: string }>;
  reset_capabilities: string[];
}

export interface TemplateGroup {
  key: string;
  title: string;
  description: string;
  fields: TemplateField[];
}

export interface BusinessTemplate {
  title: string;
  groups: TemplateGroup[];
  available_external_fields: string[];
  matchable_fields: string[];
  receivable_fields: string[];
  default_external_match_field: string;
  default_external_receive_field: string;
}

export interface ProviderCapability {
  key: string;
  name: string;
  description: string;
  connection_template: TemplateField[];
  /** 引用 ProviderManifest.business_templates 中的模板键 */
  business_template: string;
}

export interface ProviderManifest {
  key: string;
  name: string;
  description: string;
  /** 展平后的实例连接字段列表（向后兼容，供 detail 页基础连接 tab 使用） */
  instance_template: TemplateField[];
  instance_templates: Record<string, BusinessTemplate>;
  business_templates: Record<string, BusinessTemplate>;
  capabilities: ProviderCapability[];
}

export interface IntegrationInstance {
  id: number;
  name: string;
  provider_key: string;
  provider: { key: string; name: string };
  description: string;
  enabled: boolean;
  status: InstanceStatus;
  capability_status: Record<string, InstanceStatus>;
  team: number[];
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateIntegrationInstancePayload {
  name: string;
  provider_key: string;
  description?: string;
  config?: Record<string, unknown>;
  team?: number[];
  is_draft?: boolean;
}

export interface UpdateIntegrationInstancePayload {
  name?: string;
  provider_key?: string;
  description?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
  config_scope?: string;
  team?: number[];
}

export interface CapabilityExecutionError {
  code: string;
  message: string;
  retryable: boolean;
  field: string;
  external_code: string;
  external_request_id: string;
}

export interface CapabilityExecutionResult {
  success: boolean;
  summary: string;
  request_id: string;
  partial_success: boolean;
  retryable: boolean;
  payload: Record<string, unknown>;
  errors: CapabilityExecutionError[];
}

export interface TestConnectionPayload {
  provider_key: string;
  instance_status: InstanceStatus;
  capability_status: Record<string, InstanceStatus>;
  capability_results: Record<string, CapabilityExecutionResult>;
}

export interface TestConnectionResult {
  result: boolean;
  data: Omit<CapabilityExecutionResult, 'payload'> & { payload: TestConnectionPayload };
}
