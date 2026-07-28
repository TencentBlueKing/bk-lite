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
