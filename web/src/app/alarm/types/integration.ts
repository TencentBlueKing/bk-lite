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
