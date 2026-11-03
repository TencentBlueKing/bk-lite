import type { Group } from '@/types/index';

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
  space_id?: number;
  group_tree?: Group[];
  /** 分享链接配置身份的模块许可。缺省表示会话载荷不完整，不能回退到打开者的 get_client。 */
  authorized_app_names?: string[] | null;
}

/** @deprecated Use SharedCanvasDto */
export type SharedDashboardDto = SharedCanvasDto;

/** @deprecated Use CanvasShareLinkDto */
export type DashboardShareLinkDto = CanvasShareLinkDto;
