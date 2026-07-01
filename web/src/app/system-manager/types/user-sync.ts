export type RunStatus = 'running' | 'success' | 'failed' | 'partial';
export type TriggerMode = 'manual' | 'schedule';

export interface ScheduleConfig {
  enabled: boolean;
  sync_time: string;
  [key: string]: unknown;
}

export interface UserSyncSource {
  id: number;
  name: string;
  integration_instance: number;
  integration_instance_name: string;
  enabled: boolean;
  description: string;
  root_group_name: string;
  field_mapping: Record<string, unknown>;
  /** Canonical provider business parameters rendered from manifest */
  business_config?: Record<string, unknown>;
  root_scope_field?: string;
  schedule_config: ScheduleConfig | null;
  latest_run: UserSyncRun | null;
  created_by?: string;
  updated_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserSyncRun {
  id: number;
  source: number;
  trigger_mode: TriggerMode;
  status: RunStatus;
  request_id: string;
  summary: string;
  synced_user_count: number;
  synced_group_count: number;
  disabled_user_count: number;
  payload: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface AvailableInstance {
  id: number;
  name: string;
  provider_key: string;
  provider_name: string;
}

export interface PreviewResult {
  estimated_user_count: number;
  estimated_group_count?: number;
  provider_metadata?: Record<string, unknown>;
}

export interface UserSyncDepartmentNode {
  id: string;
  name: string;
  parent_id: string | null;
  children: UserSyncDepartmentNode[];
  selectable: boolean;
  is_all: boolean;
}

export interface UserSyncDepartmentOptions {
  items: UserSyncDepartmentNode[];
  selected_id: string;
  selection_missing: boolean;
}

export interface UserSyncSourceBasicFormValues {
  name: string;
  integration_instance: number;
  description: string;
  root_group_name: string;
}

export interface UserSyncSourceConfigFormValues {
  /** Dynamic manifest-driven provider business fields */
  business_config?: Record<string, unknown>;
}

export interface UserSyncSourceStrategyFormValues {
  enabled: boolean;
  schedule_enabled: boolean;
  sync_time: string;
}

export interface UserSyncSourceCreateFormValues extends UserSyncSourceBasicFormValues, UserSyncSourceConfigFormValues {
}
