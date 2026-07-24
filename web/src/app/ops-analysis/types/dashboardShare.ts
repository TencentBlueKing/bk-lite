export interface DashboardShareLinkDto {
  id: number;
  url?: string;
  permanent: boolean;
  expires_at: string | null;
  status: 'active' | 'expired' | 'revoked' | 'sharer_permission_lost' | 'dashboard_invalid';
  sharer_username: string;
}

export interface SharedDashboardDto {
  id: number;
  name: string;
  desc?: string | null;
  filters?: unknown;
  other?: Record<string, unknown>;
  view_sets: unknown;
  is_build_in: boolean;
}

