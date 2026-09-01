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
  team_id?: string;
  insecure_skip_verify?: boolean;
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
  verification?:
    | IntegrationGuideVerification
    | Array<string | IntegrationGuideStepItem>;
  troubleshooting?:
    | IntegrationGuideTroubleshootingItem[]
    | Array<string | IntegrationGuideStepItem>;
  key_reminders?: string[];
}
