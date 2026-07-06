import type { TableProps } from 'antd';
import type { Key } from 'react';

type UserStatus = 'normal' | 'disabled' | 'locked' | 'password_expired';
type ChangeUserStatusAction = 'enable' | 'disable' | 'unlock';

// 定义接口
interface UserDataType {
  id?: string;
  key: string;
  username: string;
  email: string;
  phone?: string;
  display_name: string;
  name?: string;
  team?: string;
  role?: string;
  roles: Array<{ id: string; name: string }>;
  group_role_list?: string[];
  groups: Array<any>;
  last_login?: string;
  status?: UserStatus;
  sync_source?: number | null;
}

interface ChangeUserStatusParams {
  user_ids: Key[];
  action: ChangeUserStatusAction;
}

interface ChangeUserStatusSkippedItem {
  id: number;
  reason: string;
}

interface ChangeUserStatusResponse {
  action: ChangeUserStatusAction;
  total: number;
  success_ids: number[];
  skipped: ChangeUserStatusSkippedItem[];
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
  phone?: string;
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
export type {
  Access,
  BruteForceStatus,
  ChangeUserStatusAction,
  ChangeUserStatusParams,
  ChangeUserStatusResponse,
  ChangeUserStatusSkippedItem,
  TableRowSelection,
  TransmitUserData,
  UserDataType,
  UserStatus,
};
