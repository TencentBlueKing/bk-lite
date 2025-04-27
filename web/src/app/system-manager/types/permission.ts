import type { RadioChangeEvent } from 'antd';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';

// Permission related interfaces
export interface DataPermission {
  id: string;
  name: string;
  view: boolean;
  operate: boolean;
  [key: string]: any; // Allow additional properties
}

export interface DataItem {
  id: string;
  name: string;
  description: string;
  group_id: string;
  group_name?: string;
  rules: {
    [key: string]: any;
  };
}

export interface PermissionRuleItem {
  id: string;
  name: string;
  permission: string[];
}

// Permission configuration interface
export interface PermissionConfig {
  type: string;
  allPermissions: {
    view: boolean;
    operate: boolean;
  };
  specificData: Array<DataPermission>;
}

// Modified interface definition with type discriminator
export interface ModulePermissionConfig extends PermissionConfig {
  __type?: 'module';
}

export interface ProviderPermissionConfig {
  __type?: 'provider';
  [key: string]: PermissionConfig | 'provider' | undefined; // Unified index signature
}

// Using discriminated union type
export type ModulePermission = ModulePermissionConfig | ProviderPermissionConfig;

// Permission state interface
export interface PermissionsState {
  [key: string]: ModulePermission;
}

// Pagination information interface
export interface PaginationInfo {
  current: number;
  pageSize: number;
  total: number;
}

// Interface for handling nested pagination
export interface IndexedPagination {
  [key: string]: PaginationInfo;
}

// SubModuleTabs component props interface
export interface SubModuleTabsProps {
  module: string;
  activeSubModule: string | null;
  setActiveSubModule: (subModule: string) => void;
  permissions: PermissionsState;
  moduleData: Record<string, DataPermission[]>;
  loadSpecificData: (module: string, subModule: string) => void;
  loading: { [key: string]: boolean };
  pagination: { [key: string]: PaginationInfo };
  activeKey: string;
  handleTypeChange: (e: RadioChangeEvent, module: string, subModule?: string) => void;
  handleAllPermissionChange: (e: CheckboxChangeEvent, module: string, type: 'view' | 'operate', subModule?: string) => void;
  handleSpecificDataChange: (record: DataPermission, module: string, type: 'view' | 'operate', subModule?: string) => void;
  handleTableChange: (pagination: PaginationInfo, filters: any, sorter: any, module?: string, subModule?: string) => void;
}

// ModuleContent component props interface
export interface ModuleContentProps {
  module: string;
  subModule?: string;
  permissions: PermissionsState;
  loading: { [key: string]: boolean };
  moduleData: { [key: string]: DataPermission[] };
  pagination: { [key: string]: PaginationInfo };
  activeKey: string;
  activeSubModule: string;
  handleTypeChange: (e: RadioChangeEvent, module: string, subModule?: string) => void;
  handleAllPermissionChange: (e: CheckboxChangeEvent, module: string, type: 'view' | 'operate', subModule?: string) => void;
  handleSpecificDataChange: (record: DataPermission, module: string, type: 'view' | 'operate', subModule?: string) => void;
  handleTableChange: (pagination: PaginationInfo, filters: any, sorter: any, module?: string, subModule?: string) => void;
}

// PermissionTypeSelector component props interface
export interface PermissionTypeSelectorProps {
  type: string;
  module: string;
  subModule?: string;
  handleTypeChange: (e: RadioChangeEvent, module: string, subModule?: string) => void;
  isEditable: boolean;
}

// AllPermissionsSelector component props interface
export interface AllPermissionsSelectorProps {
  currentModule?: PermissionConfig | ModulePermissionConfig;
  module: string;
  subModule?: string;
  handleAllPermissionChange: (e: CheckboxChangeEvent, module: string, type: 'view' | 'operate', subModule?: string) => void;
  isEditable: boolean;
}

// PermissionTableColumns props interface
export interface PermissionTableColumnsProps {
  handleSpecificDataChange: (record: DataPermission, module: string, type: 'view' | 'operate', subModule?: string) => void;
  activeKey: string;
  activeSubModule: string;
}

// SpecificDataTable component props interface
export interface SpecificDataTableProps {
  isEditable: boolean;
  isModuleLoading: boolean;
  dataKey: string;
  moduleData: { [key: string]: DataPermission[] };
  columns: any[];
  pagination: PaginationInfo;
  handleTableChange: (pagination: PaginationInfo, filters: any, sorter: any, module?: string, subModule?: string) => void;
  module: string;
  subModule?: string;
  activeKey: string;
  activeSubModule: string;
  handleSpecificDataChange: (record: DataPermission, module: string, type: 'view' | 'operate', subModule?: string) => void;
}

export interface PermissionRuleProps {
  value?: any;
  modules: string[];
  onChange?: (value: any) => void;
  formGroupId?: string;
}

// Permission modal related interfaces
export interface AppPermission {
  key: string;
  app: string;
  permission: number;
}

export interface PermissionModalProps {
  visible: boolean;
  rules: number[];
  node: TreeDataNode | null;
  onOk: (values: PermissionFormValues) => void;
  onCancel: () => void;
}

export interface PermissionFormValues {
  groupName: string;
  permissions: AppPermission[];
  [key: string]: any;
}
