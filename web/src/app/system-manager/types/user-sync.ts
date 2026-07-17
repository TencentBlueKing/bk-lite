export type RunStatus = 'running' | 'success' | 'failed' | 'partial';
export type TriggerMode = 'manual' | 'schedule';

export type UserSyncScheduleMode = 'disabled' | 'daily' | 'weekly' | 'interval_hours';

export interface ScheduleConfig {
  mode: UserSyncScheduleMode;
  time?: string;
  weekdays?: number[];
  interval_hours?: 1 | 2 | 3 | 4 | 6 | 8 | 12;
  timezone?: string;
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
  /** BK-Lite 平台级配置:不归 provider manifest 管 */
  platform_config?: PlatformConfig;
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
  /** BK-Lite 平台级配置:避开 provider manifest contract 校验 */
  platform_config?: PlatformConfig;
}

/** 用户同步-本地密码初始化方式配置(每个同步源独立一套) */
export type PasswordInitMode = 'none' | 'uniform' | 'random';

export interface PasswordInitConfig {
  /** 模式;空配置时 undefined,UI 默认渲染为 'none' */
  mode?: PasswordInitMode;
  /** 仅 mode=uniform 必填:管理员指定的统一初始密码 */
  uniform_password?: string;
  /** 服务端脱敏返回：已有加密统一密码，留空保存时保持不变 */
  uniform_password_configured?: boolean;
  /** 仅 mode=uniform/random 必填:通知中心邮件通道 ID */
  email_channel_id?: number;
  /** 通知中心邮件模板 key,默认走模板自带 */
  email_template_key?: string;
}

export interface PlatformConfig {
  /** 用户同步-本地密码初始化方式配置 */
  password_init?: PasswordInitConfig;
  [key: string]: unknown;
}

export interface UserSyncSourceStrategyFormValues {
  enabled: boolean;
  schedule_mode: UserSyncScheduleMode;
  time?: string;
  weekdays?: number[];
  interval_hours?: 1 | 2 | 3 | 4 | 6 | 8 | 12;
}

export interface UserSyncSourceCreateFormValues extends UserSyncSourceBasicFormValues, UserSyncSourceConfigFormValues {
}
