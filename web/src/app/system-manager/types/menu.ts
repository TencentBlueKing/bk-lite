export interface CustomMenu {
  id: number;
  app: string;
  display_name: string;
  description?: string;
  is_enabled: boolean;
  is_build_in: boolean;
  menu_count: number;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  domain?: string;
  updated_by_domain?: string;
}

export interface CustomMenuListParams {
  app: string;
  page: number;
  page_size: number;
  search?: string;
}

export interface CustomMenuListResponse {
  count: number;
  items: CustomMenu[];
}

export interface CustomMenuCreateParams {
  app: string;
  display_name: string;
  description?: string;
  is_enabled?: boolean;
}

export interface CustomMenuUpdateParams extends CustomMenuCreateParams {
  id: number;
}

// 源菜单树节点类型
export interface SourceMenuNode {
  name: string;
  display_name: string;
  url: string;
  icon?: string;
  type: 'menu' | 'page';
  tour?: {
    title: string;
    description: string;
    cover?: string;
    target: string;
    order: number;
  };
  isDetailMode?: boolean; // 是否为详情页模式
  hiddenChildren?: SourceMenuNode[]; // 详情页模式下隐藏的子菜单
  children?: SourceMenuNode[];
}

// 功能菜单项
export interface FunctionMenuItem {
  id?: number;
  name: string;
  display_name: string;
  url: string;
  icon?: string;
  type: 'menu' | 'page';
  tour?: {
    title: string;
    description: string;
    cover?: string;
    target: string;
    order: number;
  };
  isExisting?: boolean;
  originName?: string;
  isDetailMode?: boolean; // 是否为详情页模式
  hiddenChildren?: SourceMenuNode[]; // 详情页模式下隐藏的子菜单
}
