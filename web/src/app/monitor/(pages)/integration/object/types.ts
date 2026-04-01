// 对象类型
export interface MonitorObjectType {
  id: string;
  name: string; // 后端返回的 display_name 映射到这里
  description?: string;
  order: number;
  object_count?: number;
  is_builtin?: boolean; // 是否内置类型（内置类型不可编辑删除）
  created_at?: string;
  updated_at?: string;
}

// 子对象
export interface ChildObject {
  id: string;
  name: string;
  _isExisting?: boolean; // 标记是否为已存在的子对象（编辑时从后端加载的）
}

// 监控对象
export interface MonitorObjectItem {
  id: number;
  name: string;
  display_name?: string;
  icon?: string;
  type: string; // 后端返回的 type (type id)
  type_id: string; // 前端映射
  display_type?: string; // 后端返回的国际化类型名
  level?: string; // 'base' | 'derivative'
  parent?: number | null; // 父对象ID
  is_visible: boolean;
  is_builtin?: boolean; // 是否内置对象（内置对象不可编辑删除）
  order: number;
  description?: string;
  children?: ChildObject[];
  children_count?: number;
  created_at?: string;
  updated_at?: string;
}

// 创建/编辑对象类型的表单数据
export interface ObjectTypeFormData {
  id?: string; // 编辑时需要，创建时后端自动生成
  name: string; // 名称（必填）
}

// 创建/编辑对象的表单数据
export interface ObjectFormData {
  id?: number;
  name: string;
  display_name?: string;
  icon?: string;
  type_id: string;
  description?: string;
  children?: ChildObject[];
}

// API 请求参数
export interface GetObjectsParams {
  type_id?: string;
  page?: number;
  page_size?: number;
  name?: string;
}

// 排序更新参数
export interface OrderUpdateItem {
  id: string | number;
  order: number;
}
