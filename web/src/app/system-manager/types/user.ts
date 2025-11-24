import type { TableProps } from 'antd';
// 定义接口
interface UserDataType {
  id?: string;
  key: string;
  username: string;
  email: string;
  display_name: string;
  name?: string;
  team?: string;
  role?: string;
  roles: Array<{ id: string; name: string }>;
  group_role_list?: string[];
  groups: Array<any>;
  last_login?: string;
}

interface Access {
  manageGroupMembership: boolean;
  view: boolean;
  mapRoles: boolean;
  impersonate: boolean;
  manage: boolean;
}

interface BruteForceStatus {
  numFailures: number;
  disabled: boolean;
  lastIPFailure: string;
  lastFailure: number;
}

interface TransmitUserData {
  id: string;
  createdTimestamp: number;
  username: string;
  enabled: boolean;
  emailVerified: boolean;
  firstName: string;
  lastName: string;
  Number: string;
  email: string;
  access: Access;
  team: string;
  role: string;
  bruteForceStatus: BruteForceStatus;
}

// 定义组织列表的接口
type TableRowSelection<T extends object = object> =
    TableProps<T>['rowSelection'];
export type { UserDataType, TransmitUserData, TableRowSelection,Access, BruteForceStatus };
