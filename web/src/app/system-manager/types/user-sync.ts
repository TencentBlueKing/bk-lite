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
  source_name?: string;
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

// ---------------------------------------------------------------------------
// 同步进度展示 (user-sync-run-progress capability)
// ---------------------------------------------------------------------------

/** 同步进度阶段 key。控制 Drawer Steps 顺序。 */
export type PhaseKey =
  | 'fetch_directory'
  | 'sync_groups'
  | 'sync_users'
  | 'reconcile'
  | 'finalize';

/** 单阶段状态。 */
export type PhaseStatus = 'wait' | 'process' | 'finish' | 'error' | 'skipped';

/** 启动时 snapshot 的 password_init.mode。前端按此决定是否显示 finalize 阶段。 */
export type PasswordInitModeSnapshot = 'none' | 'uniform' | 'random' | null;

/** 单阶段进度 entry(对应 payload.phase_progress[phase])。 */
export interface PhaseProgressEntry {
  current: number;
  total: number;
  status: PhaseStatus;
  completed_at?: string;
  skip_reason?: string;
  /** per-phase counters,字段含义随阶段变化(sync_users vs reconcile vs sync_groups)。
   * 不再使用全局 payload.counters 顶层字段,避免对账字段提前展示。 */
  counters?: {
    // sync_users
    new_users?: number;
    updated_users?: number;
    conflict_users?: number;
    // reconcile
    disabled_users?: number;
    deleted_group_count?: number;
    // sync_groups
    created_groups?: number;
    updated_groups?: number;
  };
}

/** run.payload 中与进度展示相关的子结构(后端写入)。 */
export interface UserSyncRunProgressPayload {
  // 既有
  external_request_id?: string;
  errors?: Array<{ message?: string }>;
  input_summary?: {
    fetched_user_count?: number;
    fetched_group_count?: number;
  };
  conflict_usernames?: string[];
  conflict_user_count?: number;
  password_vault?: unknown;
  email_status?: {
    total?: number;
    sent?: number;
    failed?: number;
    completed?: boolean;
  };
  email_dispatch?: unknown;

  // 新增(本次 change)
  password_init_mode?: PasswordInitModeSnapshot;
  phase?: PhaseKey;
  phase_progress?: Partial<Record<PhaseKey, PhaseProgressEntry>>;
  phase_error?: {
    phase: PhaseKey;
    current: number;
    total: number;
    /** 由前端按当前语言映射；新记录不再持久化异常原文。 */
    error_code?: string;
    /** 兼容历史同步记录。 */
    error_message?: string;
    failed_at: string;
  };
  /** 保留顶层 counters 作向后兼容;推荐用 phase_progress.<phase>.counters(per-phase 归属) */
  counters?: {
    new_users: number;
    updated_users: number;
    disabled_users: number;
    conflict_users: number;
  };
}
