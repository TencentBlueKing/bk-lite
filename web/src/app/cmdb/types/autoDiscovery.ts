export interface CollectTaskMessage {
    add: number;
    update: number;
    delete: number;
    association: number;
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

