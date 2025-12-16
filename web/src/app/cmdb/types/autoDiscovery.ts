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
}

export interface CollectTask {
    id: number;
    name: string;
    task_type: string;
    driver_type: string;
    model_id: string;
    exec_status: number;
    updated_at: string;
    message: CollectTaskMessage;
    exec_time: string | null;
    input_method: number;
    examine: boolean,
    [permission: string]: any;
}

export interface TreeNode {
    id: string;
    model_id?: string;
    key: string;
    name: string;
    type?: string;
    task_type?: string;
    tag?: string[];
    desc?: string;
    children?: TreeNode[];
    tabItems?: TreeNode[];
}

export interface ModelItem {
    id: string;
    model_id: string;
    key: string;
    name: string;
    task_type?: string;
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
