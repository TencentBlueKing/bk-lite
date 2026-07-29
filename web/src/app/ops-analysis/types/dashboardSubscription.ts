export type DashboardSubscriptionStatus = 'active' | 'paused';

export interface DashboardSubscription {
  id: number;
  dashboard: number | null;
  creator: string;
  name: string;
  status: DashboardSubscriptionStatus;
  recipient_email: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DashboardSubscriptionPayload {
  dashboard: number;
  name: string;
  recipient_email: string;
  status: DashboardSubscriptionStatus;
}

export type DashboardSubscriptionUpdatePayload = Omit<
  DashboardSubscriptionPayload,
  'dashboard'
>;

export type DashboardExecutionStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'unknown';

export interface DashboardExecutionCreated {
  execution_id: number;
  status: DashboardExecutionStatus;
}

export interface DashboardReportExecutionSnapshot {
  dashboard_id: number;
  creator_id: string;
  subscription_id: number;
  filter_values: Record<string, unknown>;
  created_at: string;
}

export interface DashboardReportExecution {
  id: number;
  subscription: number | null;
  dashboard: number | null;
  creator: string;
  status: DashboardExecutionStatus;
  trigger_type: 'manual';
  failure_stage: string;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  snapshot: DashboardReportExecutionSnapshot | null;
}
