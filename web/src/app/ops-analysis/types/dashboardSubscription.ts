export type DashboardSubscriptionStatus = 'active' | 'paused';

export type DashboardScheduleType = 'daily' | 'weekly' | 'monthly';

export type DashboardExecutionStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'unknown';

export interface DashboardExecutionSummary {
  execution_id: number;
  status: DashboardExecutionStatus;
  trigger_type: 'manual_test' | 'scheduled';
  failure_stage: string;
  error_code: string;
  error_message: string;
  created_at: string;
  finished_at: string | null;
  scheduled_time_utc: string | null;
}

export interface DashboardSubscription {
  id: number;
  dashboard: number | null;
  creator: string;
  name: string;
  status: DashboardSubscriptionStatus;
  recipient_email: string;
  email_channel: number;
  schedule_type: DashboardScheduleType | null;
  schedule_hour: number | null;
  schedule_minute: number | null;
  schedule_weekday: number | null;
  schedule_day_of_month: number | null;
  timezone: string | null;
  next_run_at: string | null;
  version: number;
  config: Record<string, unknown>;
  latest_scheduled_execution: DashboardExecutionSummary | null;
  latest_manual_test_execution: DashboardExecutionSummary | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardSubscriptionPayload {
  dashboard: number;
  name: string;
  recipient_email: string;
  email_channel: number;
  status?: DashboardSubscriptionStatus;
  schedule_type?: DashboardScheduleType | null;
  schedule_hour?: number | null;
  schedule_minute?: number | null;
  schedule_weekday?: number | null;
  schedule_day_of_month?: number | null;
  timezone?: string | null;
  version?: number;
  applied_filter_values?: Record<string, unknown>;
}

export type DashboardSubscriptionUpdatePayload = Omit<
  DashboardSubscriptionPayload,
  'dashboard'
>;

export interface DashboardExecutionCreated {
  execution_id: number;
  status: DashboardExecutionStatus;
  request_id: string;
  created: boolean;
}

export interface DashboardReportExecutionSnapshot {
  dashboard_id: number;
  creator_id: string;
  subscription_id: number;
  filter_values: Record<string, unknown>;
  filter_semantics?: Record<string, unknown>;
  scheduled_time_utc?: string | null;
  schedule_timezone?: string;
  scheduled_local_time?: string;
  subscription_version?: number | null;
  created_at: string;
}

export interface DashboardReportExecution {
  id: number;
  subscription: number | null;
  dashboard: number | null;
  creator: string;
  status: DashboardExecutionStatus;
  trigger_type: 'manual_test' | 'scheduled';
  scheduled_time_utc?: string | null;
  failure_stage: string;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  snapshot: DashboardReportExecutionSnapshot | null;
  pdf_artifact: DashboardReportPdfArtifact | null;
}

export interface DashboardReportRenderSnapshot {
  dashboard_id: number;
  dashboard_name: string;
  dashboard_updated_at: string;
  view_sets: unknown[];
  filters: unknown;
  other: Record<string, unknown> | null;
  widget_manifest: Array<{
    widget_id: string;
    widget_type: string | null;
    datasource_id: number | string | null;
  }>;
  created_at: string;
}

export interface DashboardReportPdfArtifact {
  storage_reference: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface DashboardExecutionRenderInput {
  execution_id: number;
  input_snapshot: DashboardReportExecutionSnapshot;
  render_snapshot: DashboardReportRenderSnapshot;
}
