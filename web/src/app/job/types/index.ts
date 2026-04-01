export type DangerousRuleMatchType = 'exact' | 'regex';

export interface DangerousRulePatternItem {
  pattern?: string;
  match_pattern?: string;
  name?: string;
  match_type?: DangerousRuleMatchType;
}

export interface DangerousPathMatchTypeGroup {
  exact?: string[];
  regex?: string[];
}

export interface DangerousRule {
  id: number;
  name: string;
  description: string;
  pattern: string;
  match_type?: DangerousRuleMatchType;
  level: 'confirm' | 'forbidden';
  is_enabled: boolean;
  team: number[];
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
}

export interface DangerousRuleListResponse {
  count: number;
  items: DangerousRule[];
}

export interface DangerousRuleParams {
  page?: number;
  page_size?: number;
  search?: string;
  level?: 'confirm' | 'forbidden';
  match_type?: DangerousRuleMatchType;
  is_enabled?: boolean;
  name?: string;
  pattern?: string;
  team?: string;
}

export interface DangerousRuleFormData {
  name: string;
  description?: string;
  pattern: string;
  match_type?: DangerousRuleMatchType;
  level: 'confirm' | 'forbidden';
  is_enabled?: boolean;
  team?: number[];
}

// Enabled dangerous rules for script validation
export interface EnabledDangerousRules {
  confirm: (string | DangerousRulePatternItem)[];
  forbidden: (string | DangerousRulePatternItem)[];
}

// Enabled dangerous paths for file distribution validation
export interface EnabledDangerousPaths {
  confirm: DangerousPathMatchTypeGroup;
  forbidden: DangerousPathMatchTypeGroup;
}

export type TargetOS = 'linux' | 'windows';
export type TargetSource = 'sync' | 'manual';
export type CredentialSource = 'manual' | 'credential';
export type SSHCredentialType = 'key' | 'password';
export type WinRMScheme = 'http' | 'https';

export interface Target {
  id: number;
  name: string;
  ip: string;
  os_type: string;
  os_type_display: string;
  driver: string;
  driver_display: string;
  cloud_region_id?: number;
  cloud_region_name?: string;
  node_id: string;
  source: TargetSource;
  source_display: string;
  source_id: string;
  credential_source: string;
  credential_source_display: string;
  ssh_credential_type: string;
  ssh_credential_type_display: string;
  ssh_port: number;
  ssh_user: string;
  ssh_key_file: string | null;
  ssh_key_file_name: string;
  credential_id: string;
  winrm_port: number;
  winrm_scheme: string;
  winrm_scheme_display: string;
  winrm_user: string;
  winrm_cert_validation: boolean;
  team: number[];
  team_name: string[];
  created_by: string;
  created_at?: string;
  updated_by: string;
  updated_at?: string;
}

export interface TargetListResponse {
  count: number;
  items: Target[];
}

export interface TargetParams {
  page?: number;
  page_size?: number;
  search?: string;
  name?: string;
  ip?: string;
  os_type?: string;
  driver?: string;
  source?: TargetSource;
}

export interface TargetFormData {
  name: string;
  ip: string;
  os_type: TargetOS;
  cloud_region_id: string;
  driver: string;
  credential_source: CredentialSource;
  credential_id?: string;
  ssh_port: number;
  ssh_user: string;
  ssh_credential_type: SSHCredentialType;
  ssh_password?: string;
  ssh_key_file?: File;
  winrm_port: number;
  winrm_scheme: WinRMScheme;
  winrm_user: string;
  winrm_password?: string;
  winrm_cert_validation: boolean;
  team: number[];
}

// Script types
export type ScriptType = 'shell' | 'bat' | 'python' | 'powershell';

export interface ScriptParam {
  name: string;
  description?: string;
  default?: string;
  is_encrypted?: boolean;
}

export interface Script {
  id: number;
  name: string;
  description: string;
  script_type: ScriptType;
  script_type_display: string;
  os: 'linux' | 'windows';
  os_display: string;
  content: string;
  params: ScriptParam[];
  timeout: number;
  team: number[];
  team_name: string[];
  is_preset: boolean;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
}

export interface DashboardTrend {
  date: string;
  execution_count: number;
  success_count: number;
  failed_count: number;
}

export interface DashboardSuccessRatePeriod {
  execution_total: number;
  success_count: number;
  failed_count: number;
  success_rate: number;
}

export interface DashboardSuccessRateCompare {
  days: number;
  current_period: DashboardSuccessRatePeriod;
  success_rate_increase: number;
}

export interface ScriptListResponse {
  count: number;
  items: Script[];
}

export interface ScriptFormData {
  name: string;
  description?: string;
  script_type: ScriptType;
  content: string;
  params: ScriptParam[];
  team: number[];
}

export interface ScriptParams {
  page?: number;
  page_size?: number;
  name?: string;
  script_type?: ScriptType;
  created_by?: string;
  description?: string;
  team?: string;
}

// Playbook types
export interface FileTreeNode {
  name: string;
  type: 'file' | 'directory';
  children?: FileTreeNode[];
}

export interface PlaybookParam {
  name: string;
  default?: string;
  description?: string;
}

export interface Playbook {
  id: number;
  name: string;
  description: string;
  version: string;
  readme?: string;
  file_list?: FileTreeNode[];
  params: PlaybookParam[];
  file_name: string;
  file_key: string;
  bucket_name: string;
  file_size: number;
  entry_file: string;
  timeout: number;
  team: number[];
  team_name: string[];
  is_preset: boolean;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
}

export interface PlaybookListResponse {
  count: number;
  items: Playbook[];
}

export interface PlaybookParams {
  page?: number;
  page_size?: number;
  name?: string;
  search?: string;
  created_by?: string;
  description?: string;
  team?: string;
}

export interface PlaybookFormData {
  name?: string;
  description?: string;
  team?: number[];
}

// Scheduled Task types
export type JobType = 'script' | 'playbook' | 'file';
export type ScheduleType = 'once' | 'cron';

export interface ScheduledTask {
  id: number;
  name: string;
  description: string;
  job_type: JobType;
  job_type_display: string;
  schedule_type: ScheduleType;
  schedule_type_display: string;
  cron_expression: string;
  scheduled_time: string;
  is_enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  run_count: number;
  target_count: number;
  created_by: string;
  created_at: string;
}

export interface ScheduledTaskListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: ScheduledTask[];
  items?: ScheduledTask[];
}

export interface ScheduledTaskParams {
  page?: number;
  page_size?: number;
  search?: string;
  name?: string;
  job_type?: JobType;
  schedule_type?: ScheduleType;
  is_enabled?: boolean;
}

export interface ScheduledTaskFile {
  name: string;
  file_key: string;
  bucket_name: string;
  size: number;
}

export interface ScheduledTaskFormData {
  name: string;
  description?: string;
  job_type: JobType;
  schedule_type: ScheduleType;
  cron_expression?: string;
  scheduled_time?: string;
  script?: number;
  playbook?: number;
  target_source: ExecutionTargetSource;
  target_list: TargetListItem[];
  params?: Record<string, unknown>;
  script_type?: ScriptType;
  script_content?: string;
  files?: ScheduledTaskFile[];
  target_path?: string;
  timeout?: number;
  is_enabled?: boolean;
  team?: number[];
}

// Job Record types
export type JobRecordStatus = 'pending' | 'running' | 'success' | 'failed' | 'canceled';
export type JobRecordSource = 'manual' | 'scheduled' | 'api';

export interface ExecutionTarget {
  id: number;
  target: number;
  target_name: string;
  target_ip: string;
  status: JobRecordStatus;
  status_display: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  started_at: string | null;
  finished_at: string | null;
  error_message: string;
}

export interface JobRecordFile {
  name: string;
  file_key: string;
  bucket_name: string;
  size: number;
}

export interface JobRecord {
  id: number;
  name: string;
  job_type: JobType;
  job_type_display: string;
  source?: JobRecordSource;
  source_display?: string;
  trigger_source?: string;
  trigger_source_display?: string;
  status: JobRecordStatus;
  status_display: string;
  created_by: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration?: number | null;
  target_count?: number;
  total_count?: number;
  success_count: number;
  failed_count: number;
  created_at: string;
  updated_by?: string;
  updated_at?: string;
}

export interface JobRecordDetail extends JobRecord {
  script?: number;
  playbook?: number;
  params?: Record<string, unknown>;
  script_type?: ScriptType;
  script_type_display?: string;
  script_content?: string;
  files?: JobRecordFile[];
  target_path?: string;
  timeout?: number;
  team?: number[];
  executor_user?: string;
  execution_targets: ExecutionTarget[];
  execution_results?: any[];
  target_list?: any[];
}

export interface JobRecordListResponse {
  count: number;
  next?: string | null;
  previous?: string | null;
  items: JobRecord[];
  results?: JobRecord[];
}

export interface JobRecordParams {
  page?: number;
  page_size?: number;
  search?: string;
  name?: string;
  job_type?: JobType;
  source?: JobRecordSource;
  status?: JobRecordStatus;
  created_by?: string;
  started_at_after?: string;
  started_at_before?: string;
}

// Execution target types
export type ExecutionTargetSource = 'node_mgmt' | 'manual' | 'sync';

export interface TargetListItem {
  node_id?: string;
  target_id?: number;
  name?: string;
  ip?: string;
  os?: 'linux' | 'windows';
  cloud_region_id?: number;
}
