interface AuthConfig {
  type: string;
  token: string;
  password: string;
  username: string;
  secret_key: string;
}
interface Config {
  url: string;
  params: Record<string, any>;
  auth: AuthConfig;
  method: string;
  headers: Record<string, any>;
  timeout: number;
  content_type: string;
  examples: any;
  event_fields_mapping: Record<string, string>;
  event_fields_desc_mapping: Record<string, string>;
}

export interface K8sDownloadFile {
  key: string;
  file_name: string;
  display_name: string;
}

export interface K8sMeta {
  source_id: string;
  name: string;
  description: string;
  receiver_url: string;
  method: string;
  headers: Record<string, string>;
  push_source_id_default: string;
  push_source_id_configurable: boolean;
  image_reference: string;
  download_files: K8sDownloadFile[];
  notes: string[];
}

export interface K8sRenderParams {
  server_url: string;
  cluster_name: string;
  push_source_id?: string;
  team_secret?: string;
  insecure_skip_verify?: boolean;
}

export interface SnmpTrapNodeItem {
  id?: number | string;
  name?: string;
  ip?: string;
  [key: string]: any;
}

export interface SnmpTrapNodeListResponse {
  nodes?: SnmpTrapNodeItem[];
}

export interface IntegrationGuideStepItem {
  title?: string;
  description?: string;
  content?: string;
}

export interface IntegrationGuideSetupStep {
  title?: string;
  items?: string[];
}

export interface IntegrationGuideParameterMappingItem {
  parameter?: string;
  name?: string;
  target_field?: string;
  field?: string;
  value?: string;
  description?: string;
  required?: boolean;
}

export interface IntegrationGuideVerificationCheck {
  title?: string;
  summary?: string;
  expected_results?: string[];
  steps?: string[];
}

export interface IntegrationGuideVerification {
  curl_check?: IntegrationGuideVerificationCheck;
  problem_check?: IntegrationGuideVerificationCheck;
  recovery_check?: IntegrationGuideVerificationCheck;
}

export interface IntegrationGuideFieldMappingItem {
  bk_lite_field?: string;
  zabbix_field?: string;
  upstream_source?: string;
}

export interface IntegrationGuideTroubleshootingItem {
  symptom?: string;
  cause?: string;
  action?: string;
  possible_causes?: string[];
  resolutions?: string[];
}

export interface AlertSourceIntegrationGuide {
  source_type: string;
  source_id: string;
  webhook_url?: string;
  headers?: Record<string, string>;
  description?: string;
  media_type_parameters?: string[];
  setup_steps?: IntegrationGuideSetupStep[];
  parameter_guidance?: IntegrationGuideParameterMappingItem[];
  parameter_mapping?: IntegrationGuideParameterMappingItem[];
  field_mappings?: IntegrationGuideFieldMappingItem[];
  script_template?: string;
  steps?: Array<string | IntegrationGuideStepItem>;
  verification?: IntegrationGuideVerification | Array<string | IntegrationGuideStepItem>;
  troubleshooting?: IntegrationGuideTroubleshootingItem[] | Array<string | IntegrationGuideStepItem>;
  key_reminders?: string[];
}

export interface SourceItem {
  id: number;
  event_count: number | null | undefined | string;
  last_event_time: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  name: string;
  source_id: string;
  source_type: string;
  config: Config;
  secret: string;
  logo: string | null;
  access_type: string;
  is_active: boolean;
  is_effective: boolean;
  description: string;
}

export interface RawEventData {
    item: string;
    level: string;
    title: string;
    value: number;
    labels: Record<string, string>;
    status: string;
    end_time: string;
    start_time: string;
    annotations: Record<string, string>;
    description: string;
    external_id: string;
    resource_id: number;
    resource_name: string;
    resource_type: string;
}

export interface EventTableItem {
    id: number;
    start_time: string;
    end_time: string;
    source_name: string;
    raw_data: RawEventData;
    received_at: string;
    title: string;
    description: string;
    level: string;
    action: string;
    rule_id: number | null;
    event_id: string;
    external_id: string;
    item: string;
    resource_id: string;
    resource_type: string;
    resource_name: string;
    status: string;
    assignee: string[];
    value: number;
    source: number;
}

export interface TeamSecretItem {
    team_id: string;
    team_name: string;
    secret: string;
}

export interface TeamSecretsResponse {
    team_secrets: TeamSecretItem[];
}

export interface TeamSecretResponse {
    team_id: string;
    secret: string;
}
