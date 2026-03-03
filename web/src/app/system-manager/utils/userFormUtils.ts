import type { DataNode as TreeDataNode } from 'antd/lib/tree';

export interface GroupRole {
  id: number;
  name: string;
  app: string;
}

export interface GroupRules {
  [groupId: string]: { [app: string]: number };
}

export interface TreeSelectNode {
  title: string;
  value: number;
  key: number;
  children: TreeSelectNode[];
}

export interface UserFormPayload {
  username?: string;
  email?: string;
  lastName?: string;
  locale?: string;
  timezone?: string;
  groups?: number[];
  roles: number[];
  rules?: number[];
  is_superuser: boolean;
}

export interface UserDetailResponse {
  username?: string;
  email?: string;
  display_name?: string;
  timezone?: string;
  locale?: string;
  is_superuser?: boolean;
  groups?: Array<{ id: number; rules?: { [key: string]: number } }>;
  roles?: Array<{ role_id: number }>;
}

/**
 * Transform tree data for TreeSelect component
 * Converts TreeDataNode format to TreeSelect-compatible format
 */
export function transformTreeDataForSelect(data: TreeDataNode[]): TreeSelectNode[] {
  return data.map((node: TreeDataNode) => ({
    title: (node.title as string) || 'Unknown',
    value: node.key as number,
    key: node.key as number,
    children: node.children ? transformTreeDataForSelect(node.children as TreeDataNode[]) : [],
  }));
}

/**
 * Process role tree data with organization role highlighting
 * Marks roles that come from organization as disabled
 */
export function processRoleTreeData(
  roleData: Array<{ id: number; name: string; children: Array<{ id: number; name: string }> }>,
  orgRoleIds: number[]
): TreeDataNode[] {
  return roleData.map((item) => ({
    key: item.id,
    title: item.name,
    selectable: false,
    children: item.children.map((child) => ({
      key: child.id,
      title: child.name,
      selectable: true,
      disabled: orgRoleIds.includes(child.id),
    })),
  }));
}

/**
 * Extract group IDs from user detail response
 */
export function extractGroupIds(userDetail: UserDetailResponse): number[] {
  return userDetail.groups?.map((group) => group.id) || [];
}

/**
 * Extract personal role IDs from user detail response
 */
export function extractPersonalRoleIds(userDetail: UserDetailResponse): number[] {
  return userDetail.roles?.map((role) => role.role_id) || [];
}

/**
 * Extract organization role IDs from group role data
 */
export function extractOrgRoleIds(groupRoleData: GroupRole[]): number[] {
  return groupRoleData.map((role) => role.id);
}

/**
 * Build group rules object from user detail
 */
export function buildGroupRulesFromUserDetail(userDetail: UserDetailResponse): GroupRules {
  return (
    userDetail.groups?.reduce((acc: GroupRules, group) => {
      acc[group.id] = group.rules || {};
      return acc;
    }, {}) || {}
  );
}

/**
 * Build form values from user detail for editing
 */
export function buildFormValuesFromUserDetail(
  userDetail: UserDetailResponse,
  allRoles: number[],
  groupIds: number[]
): Record<string, unknown> {
  return {
    ...userDetail,
    lastName: userDetail.display_name,
    zoneinfo: userDetail.timezone,
    roles: allRoles,
    groups: groupIds,
    is_superuser: userDetail.is_superuser || false,
  };
}

/**
 * Build payload for creating/updating user
 * Handles superuser vs normal user logic
 */
export function buildUserPayload(
  formData: Record<string, unknown>,
  organizationRoleIds: number[],
  groupRules: GroupRules,
  isSuperuser: boolean
): UserFormPayload {
  const { zoneinfo, ...restData } = formData;

  if (isSuperuser) {
    return {
      ...restData,
      roles: [],
      timezone: zoneinfo as string,
      is_superuser: true,
    } as UserFormPayload;
  }

  const personalRoles = ((formData.roles as number[]) || []).filter(
    (roleId: number) => !organizationRoleIds.includes(roleId)
  );

  const rules = Object.values(groupRules)
    .filter((group) => group && typeof group === 'object' && Object.keys(group).length > 0)
    .flatMap((group) => Object.values(group))
    .filter((rule) => typeof rule === 'number');

  return {
    ...restData,
    roles: personalRoles,
    rules,
    timezone: zoneinfo as string,
    is_superuser: false,
  } as UserFormPayload;
}

/**
 * Filter personal roles from selected roles by excluding organization roles
 */
export function filterPersonalRoles(selectedRoles: number[], orgRoleIds: number[]): number[] {
  return selectedRoles.filter((roleId) => !orgRoleIds.includes(roleId));
}

/**
 * Merge personal roles with organization roles
 */
export function mergeRoles(personalRoles: number[], orgRoleIds: number[]): number[] {
  return [...personalRoles, ...orgRoleIds];
}
