export interface TransferTask {
  task_id: string;
  type: 'import' | 'export';
  model_id: string;
  model_name: string;
  team_id: number;
  scope?: 'all' | 'selected' | 'currentPage';
  filename: string;
  status: 'queued' | 'running' | 'succeeded' | 'partial_success' | 'failed' | 'interrupted' | 'cancelled';
  phase: string;
  processed_rows: number;
  total_rows: number | null;
  summary: Record<string, number | string | null>;
  failure?: {
    stage: string;
    error_type: string;
    result_uncertain: boolean;
    execution_pending: boolean;
  } | null;
  message: string;
  available_actions: string[];
  created_at: string;
  finished_at: string | null;
  expires_at: string;
}

export interface TransferList {
  items: TransferTask[];
  can_submit: boolean;
  limits?: { active: number };
}

export interface TransferExportRequest {
  model_id: string;
  scope: 'all' | 'selected' | 'currentPage';
  inst_uuids: string[];
  attr_list: string[];
  association_list: string[];
}
