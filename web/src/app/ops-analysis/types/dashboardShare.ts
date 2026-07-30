export type CanvasShareResourceType =
  | 'dashboard'
  | 'screen'
  | 'topology'
  | 'architecture'
  | 'report'
  | 'networkTopology';

export interface CanvasShareLinkDto {
  id: number;
  url: string;
  status: 'active' | 'sharer_permission_lost' | 'dashboard_invalid';
  sharer_username: string;
  resource_type: CanvasShareResourceType;
}

export interface SharedCanvasDto {
  resource_type: CanvasShareResourceType;
  id: number;
  name: string;
  desc?: string | null;
  filters?: unknown;
  other?: Record<string, unknown>;
  view_sets: unknown;
  is_build_in: boolean;
  refresh_interval?: number;
  status?: string;
}

/** @deprecated Use SharedCanvasDto */
export type SharedDashboardDto = SharedCanvasDto;

/** @deprecated Use CanvasShareLinkDto */
export type DashboardShareLinkDto = CanvasShareLinkDto;
