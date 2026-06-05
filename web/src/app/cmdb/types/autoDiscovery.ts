export interface CollectTaskMessage {
  all: number;
  add: number;
  update: number;
  delete: number;
  association: number;
  add_error: number;
  add_success: number;
  delete_error: number;
  delete_success: number;
  update_error: number;
  update_success: number;
  association_error: number;
  association_success: number;
  message?: string;
  last_time?: string;
}

export interface CredentialPoolItem {
  credential_id?: string;
  _client_id?: string;
  username?: string;
  user?: string;
  password?: string;
  port?: number | string;
  database?: string;
  version?: string;
  level?: string;
  integrity?: string;
  privacy?: string;
  community?: string;
  authkey?: string;
  privkey?: string;
  snmp_port?: number | string;
  [key: string]: any;
}

export interface CollectTask {
  id: number;
  name: string;
  task_type: string;
  driver_type: string;
  model_id: string;
  exec_status: number;
  data_cleanup_strategy?: string;
  expire_days?: number;
  updated_at: string;
  message: CollectTaskMessage;
  exec_time: string | null;
  input_method: number;
  examine: boolean,
  credential?: CredentialPoolItem | CredentialPoolItem[];
  [permission: string]: any;
}

export interface TreeNode {
  id: string;
  model_id?: string;
  target_model_id?: string;
  key: string;
  name: string;
  type?: string;
  task_type?: string;
  encrypted_fields?: string[];
  tag?: string[];
  desc?: string;
  children?: TreeNode[];
  tabItems?: TreeNode[];
}

export interface ModelItem {
  id: string;
  model_id: string;
  target_model_id?: string;
  key: string;
  name: string;
  type?: string;
  task_type?: string;
  encrypted_fields?: string[];
  tag?: string[];
  desc?: string;
  tabItems?: TreeNode[];
};

export interface TaskStatusStats {
  success: number;
  failed: number;
  running: number;
}

export type TaskStatusMap = Record<string, TaskStatusStats>;

export interface TaskStats {
  running: number;
  success: number;
  failed: number;
}

export interface BaseTaskFormProps {
  children?: React.ReactNode;
  showAdvanced?: boolean;
  timeoutProps?: {
    min?: number;
    defaultValue?: number;
    addonAfter?: string;
  };
  modelId: string;
  submitLoading?: boolean;
  onClose: () => void;
  onTest?: () => void;
}

export interface TaskData {
  data: any[];
  count: number;
}

export interface TaskDetailData {
  add: TaskData;
  update: TaskData;
  delete: TaskData;
  relation: TaskData;
  raw_data?: TaskData;
}

export interface TaskTableProps {
  type: string;
  taskId: number;
  columns: any[];
  data: any[];
}

export interface StatisticCardConfig {
  title: string;
  value: number;
  bgColor: string;
  borderColor: string;
  valueColor: string;
  failedCount?: number;
  showFailed?: boolean;
}

export interface NodeMgmtSyncTask {
  id: number;
  name: string;
  is_builtin: boolean;
  auto_sync_enabled: boolean;
  auto_collect_enabled: boolean;
  sync_interval_minutes: number;
  collect_interval_minutes: number;
  last_sync_at: string | null;
  last_collect_at: string | null;
}

export type NodeMgmtSyncConfig = NodeMgmtSyncTask;

export type NodeMgmtSyncSummary = CollectTaskMessage;

export interface NodeMgmtSyncItem {
  id?: string | number;
  inst_name?: string;
  ip_addr?: string;
  cloud_name?: string;
  organization?: Array<number | string>;
  _status?: string;
  _error?: string;
  [key: string]: any;
}

export interface NodeMgmtSyncDetailData {
  add?: TaskData;
  update?: TaskData;
  delete?: TaskData;
  relation?: TaskData;
  raw_data?: TaskData;
  todo?: Array<Record<string, any>>;
  executed?: Array<Record<string, any>>;
}

export interface NodeMgmtSyncRun {
  id: number | null;
  task_id?: number | null;
  run_type: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: CollectTaskMessage;
  summary: NodeMgmtSyncSummary;
  detail: NodeMgmtSyncDetailData;
  error_message: string;
}

export interface NodeMgmtSyncDisplayPayload {
  task: NodeMgmtSyncTask;
  display_source: string;
  display_schema: string;
  message: CollectTaskMessage;
  summary: NodeMgmtSyncSummary;
  detail: NodeMgmtSyncDetailData;
  run: NodeMgmtSyncRun;
}
