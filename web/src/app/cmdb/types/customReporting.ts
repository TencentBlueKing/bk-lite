export type CustomReportingMode = 'standard' | 'quick';

export type CustomReportingCleanupStrategy = 'none' | 'expire' | 'snapshot';

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

export interface CustomReportingCredential {
  id: number;
  name: string;
  credential_type: string;
  credential_data: Record<string, any>;
  is_enabled: boolean;
   last_used_at?: string | null;
   created_at?: string;
   updated_at?: string;
}

export interface CustomReportingCredentialResponse {
  credential: CustomReportingCredential;
  token?: string;
}

export interface CustomReportingCredentialRevokeResponse {
  credential_id: number;
  is_enabled: boolean;
}

export interface CustomReportingTask {
  id: number;
  name: string;
  team: number[];
  config: CustomReportingTaskConfig;
  is_enabled: boolean;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  last_reported_at?: string | null;
  status?: 'receiving' | 'pending_review' | 'no_report';
  recent_batch_trend?: number[];
  credential?: CustomReportingCredential;
  token?: string;
}

export interface CustomReportingStats {
  total: number;
  receiving: number;
  pending_review: number;
}

export interface CustomReportingFieldRegistrationItem {
  attr_id: string;
  attr_name: string;
  recommended_type: string;
  is_undefined: boolean;
  first_seen_at?: string | null;
}

export interface CustomReportingTaskListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: CustomReportingTask[];
}

export interface CustomReportingCreateTaskPayload {
  name: string;
  team: number[];
  config: CustomReportingTaskConfig;
  quick_model?: CustomReportingQuickModelDraft;
  is_enabled: boolean;
}

export type CustomReportingUpdateTaskPayload = Partial<CustomReportingCreateTaskPayload>;

export interface CustomReportingOnboardingDocument {
  endpoint: string;
  auth_header: {
    name: string;
    format: string;
  };
  identity_keys: string[];
  examples: {
    instances: { instances: Array<Record<string, any>> };
    with_relations: {
      instances: Array<Record<string, any>>;
      relations: Array<Record<string, any>>;
    };
  };
}

export interface CustomReportingBatch {
  id: number;
  task_id: number;
  status: string;
  summary: Record<string, any>;
  created_at: string;
  updated_at: string;
  cleanup_reviews?: CustomReportingCleanupReview[];
}

export interface CustomReportingCleanupReview {
  id: number;
  batch_id: number;
  status: string;
  review_payload: Record<string, any>;
  reviewed_by?: string;
  reviewed_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CustomReportingReviewStatusSummary {
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}

export interface CustomReportingTaskDetail extends CustomReportingTask {
  last_reported_at?: string | null;
  credential?: CustomReportingCredential | null;
  recent_batches: CustomReportingBatch[];
  review_status_summary: CustomReportingReviewStatusSummary;
}

export interface CustomReportingBatchActivityResponse {
  task_id: number;
  batches: CustomReportingBatch[];
  cleanup_reviews: CustomReportingCleanupReview[];
  review_status_summary: CustomReportingReviewStatusSummary;
}
