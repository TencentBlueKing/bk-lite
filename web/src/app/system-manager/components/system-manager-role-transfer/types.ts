import type { DataNode as TreeDataNode } from 'antd/lib/tree';

export interface PermissionData {
  id: string;
  name: string;
  view: boolean;
  operate: boolean;
  [key: string]: any;
}

export interface AppPermission {
  key: string;
  app: string;
  permission: number;
}

export interface PermissionFormValues {
  groupName: string;
  permissions: AppPermission[];
  [key: string]: any;
}

export interface PermissionModalProps {
  visible: boolean;
  rules: { [app: string]: number };
  node: TreeDataNode | null;
  onOk: (values: PermissionFormValues) => void;
  onCancel: () => void;
}
