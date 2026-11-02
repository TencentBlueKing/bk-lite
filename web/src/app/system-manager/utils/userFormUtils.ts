import React from 'react';
import { Tag } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import dayjs from 'dayjs';

interface UserGroupTreeDataNode extends TreeDataNode {
  isVirtual?: boolean;
  syncSource?: number | null;
}

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
  value: React.Key;
  key: React.Key;
  isVirtual?: boolean;
  syncSource?: number | null;
  children: TreeSelectNode[];
}

export interface UserFormPayload {
  username?: string;
  email?: string;
  phone?: string;
  lastName?: string;
  locale?: string;
  timezone?: string;
  groups?: React.Key[];
  roles: number[];
  rules?: number[];
  is_superuser: boolean;
}

export interface UserDetailResponse {
  username?: string;
  email?: string;
  phone?: string;
  display_name?: string;
  timezone?: string;
  locale?: string;
  is_superuser?: boolean;
  sync_source?: number | null;
  manager_username?: string;
  employment_status?: string;
  job_title?: string;
  job_level?: string;
  employee_no?: string;
  account_expires_at?: string | null;
  custom_fields?: Array<{ key: string; field_type: string; value?: string }>;
  groups?: Array<{ id: React.Key; rules?: { [key: string]: number } }>;
  roles?: Array<{ role_id: number }>;
}

/**
 * Transform tree data for TreeSelect component
 * Converts TreeDataNode format to TreeSelect-compatible format
 */
export function transformTreeDataForSelect(data: TreeDataNode[]): TreeSelectNode[] {
  return data.map((node: TreeDataNode) => {
    const groupNode = node as UserGroupTreeDataNode;
    return {
      title: (node.title as string) || 'Unknown',
      value: node.key,
      key: node.key,
      isVirtual: groupNode.isVirtual === true,
      syncSource: groupNode.syncSource,
      children: node.children ? transformTreeDataForSelect(node.children as TreeDataNode[]) : [],
    };
  });
}

/**
 * Exclude synced groups when assigning a local user. A retained synced child
 * also keeps its ancestors visible so historic memberships can be displayed.
 */
export function filterSyncedGroupsForLocalUser(
  nodes: TreeSelectNode[],
  retainedGroupIds: React.Key[] = []
): TreeSelectNode[] {
  const retainedIds = new Set(retainedGroupIds.map(String));

  return nodes.reduce<TreeSelectNode[]>((result, node) => {
    const children = filterSyncedGroupsForLocalUser(node.children, retainedGroupIds);
    const isSyncedGroup = node.syncSource !== null && node.syncSource !== undefined;
    const shouldKeep = !isSyncedGroup || retainedIds.has(String(node.key)) || children.length > 0;

    if (shouldKeep) {
      result.push({ ...node, children });
    }

    return result;
  }, []);
}

export function flattenTreeSelectNodes(nodes: TreeSelectNode[]): TreeSelectNode[] {
  return nodes.reduce<TreeSelectNode[]>((acc, node) => {
    acc.push(node);
    if (node.children.length > 0) {
      acc.push(...flattenTreeSelectNodes(node.children));
    }
    return acc;
  }, []);
}

export function hasNormalGroupSelection(groupIds: React.Key[], treeData: TreeSelectNode[]): boolean {
  if (groupIds.length === 0) {
    return false;
  }

  const groupMap = new Map(flattenTreeSelectNodes(treeData).map((node) => [String(node.key), node]));
  return groupIds.some((groupId) => groupMap.get(String(groupId))?.isVirtual !== true);
}

/**
 * Process role tree data with organization role highlighting
 * Marks roles that come from organization as disabled
 */
export function processRoleTreeData(
  roleData: Array<{ id: number; name: string; display_name?: string; is_build_in?: boolean; children: Array<{ id: number; name: string }> }>,
  externalAppLabel = 'External App'
): TreeDataNode[] {
  return roleData.map((item) => ({
    key: item.id,
    title: item.is_build_in === false
      ? React.createElement('span', null, item.name, React.createElement(Tag, { color: 'green', className: 'ml-1', style: { fontSize: 11, padding: '0 4px' } }, externalAppLabel))
      : item.name,
    display_name: item.display_name,
    selectable: false,
    children: item.children.map((child) => ({
      key: child.id,
      title: child.name,
      selectable: true,
    })),
  }));
}

/**
 * Extract group IDs from user detail response
 */
export function extractGroupIds(userDetail: UserDetailResponse): React.Key[] {
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
      acc[String(group.id)] = group.rules || {};
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
  groupIds: React.Key[]
): Record<string, unknown> {
  return {
    ...userDetail,
    lastName: userDetail.display_name,
    zoneinfo: userDetail.timezone,
    roles: allRoles,
    groups: groupIds,
    is_superuser: userDetail.is_superuser || false,
    manager_username: userDetail.manager_username || '',
    employment_status: userDetail.employment_status || 'unspecified',
    job_title: userDetail.job_title || '',
    job_level: userDetail.job_level || '',
    employee_no: userDetail.employee_no || '',
    account_expires_at: userDetail.account_expires_at ? dayjs(userDetail.account_expires_at) : null,
    custom_fields: Object.fromEntries(
      (userDetail.custom_fields || []).map((item) => [
        item.key,
        item.field_type === 'date' && item.value ? dayjs(item.value) : (item.value || ''),
      ]),
    ),
  };
}

/**
 * Build payload for creating/updating user
 * Handles superuser vs normal user logic
 */
export function buildUserPayload(
  formData: Record<string, unknown>,
  personalRoleIds: number[],
  groupRules: GroupRules,
  isSuperuser: boolean
): UserFormPayload {
  const { zoneinfo, account_expires_at, custom_fields, manager_username, ...restData } = formData;
  const managerName = typeof manager_username === 'string' ? manager_username.trim() : '';
  const normalizedCustomFields = custom_fields && typeof custom_fields === 'object'
    ? Object.fromEntries(
      Object.entries(custom_fields as Record<string, unknown>).map(([key, value]) => [
        key,
        dayjs.isDayjs(value) ? value.format('YYYY-MM-DD') : value,
      ]),
    )
    : undefined;
  const expiry = dayjs.isDayjs(account_expires_at)
    ? account_expires_at.toISOString()
    : (account_expires_at ?? null);

  if (isSuperuser) {
    return {
      ...restData,
      roles: [],
      timezone: zoneinfo as string,
      manager_username: managerName,
      is_superuser: true,
      account_expires_at: expiry,
      ...(normalizedCustomFields ? { custom_fields: normalizedCustomFields } : {}),
    } as UserFormPayload;
  }

  const rules = Object.values(groupRules)
    .filter((group) => group && typeof group === 'object' && Object.keys(group).length > 0)
    .flatMap((group) => Object.values(group))
    .filter((rule) => typeof rule === 'number');

  return {
    ...restData,
    roles: personalRoleIds,
    rules,
    timezone: zoneinfo as string,
    manager_username: managerName,
    is_superuser: false,
    account_expires_at: expiry,
    ...(normalizedCustomFields ? { custom_fields: normalizedCustomFields } : {}),
  } as UserFormPayload;
}

/**
 * Merge personal roles with organization roles
 */
export function mergeRoles(personalRoles: number[], orgRoleIds: number[]): number[] {
  return [...personalRoles, ...orgRoleIds];
}
