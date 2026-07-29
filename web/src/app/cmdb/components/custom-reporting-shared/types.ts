export type CustomReportingMode = 'standard' | 'quick';

export type CustomReportingCleanupStrategy =
  | 'none'
  | 'expire'
  | 'snapshot';

export interface CustomReportingQuickModelDraft {
  model_id: string;
  model_name: string;
  identity_keys: string[];
  [key: string]: any;
}

export interface CustomReportingTaskConfig {
  mode: CustomReportingMode;
  model_id?: string;
  identity_keys?: string[];
  cleanup_strategy?: CustomReportingCleanupStrategy;
  expire_days?: number | null;
  snapshot_delete_ratio_threshold?: number | null;
  quick_model?: CustomReportingQuickModelDraft;
  [key: string]: any;
}

export interface CustomReportingReviewStatusSummary {
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}

export interface CustomReportingTaskSummaryLike {
  name: string;
  config: CustomReportingTaskConfig;
  updated_at: string;
  last_reported_at?: string | null;
}
