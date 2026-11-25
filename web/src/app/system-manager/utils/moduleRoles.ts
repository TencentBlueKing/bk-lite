import type { Group } from '@/types/index';
import { getClientIdFromRoute, mapClientName } from '@/utils/route';

export const MODULE_ADMIN_ROLE = 'module_admin';
export const MODULE_AUDITOR_ROLE = 'module_auditor';

export function moduleClientIdFromPath(pathname?: string | null): string {
  return mapClientName(getClientIdFromRoute(pathname));
}

const MODULE_PRIVILEGE_EXCLUDED = new Set(['system-manager', 'ops-console']);

export function hasModulePrivilege(roles: string[] | undefined, pathname?: string | null): boolean {
  const clientId = moduleClientIdFromPath(pathname);
  if (!clientId || MODULE_PRIVILEGE_EXCLUDED.has(clientId)) {
    return false;
  }
  const names = roles || [];
  return names.includes(`${clientId}--${MODULE_ADMIN_ROLE}`) || names.includes(`${clientId}--${MODULE_AUDITOR_ROLE}`);
}

export function containsAuthorizedGroup(nodes: Group[], id: string): boolean {
  return nodes.some((node) =>
    (String(node.id) === id && Boolean(node.hasAuth))
    || Boolean(node.subGroups && containsAuthorizedGroup(node.subGroups, id)),
  );
}

export function isModuleReadOnly(roles: string[] | undefined, pathname?: string | null, platformAdmin = false): boolean {
  if (platformAdmin || !hasModulePrivilege(roles, pathname)) return false;
  const names = roles || [];
  const clientId = moduleClientIdFromPath(pathname);
  return names.includes('auditor') || !names.includes(`${clientId}--${MODULE_ADMIN_ROLE}`);
}

export function canAssignModuleRoles(isSuperUser?: boolean): boolean {
  return Boolean(isSuperUser);
}

export function resolveOperableGroupTree(
  groupTree: Group[] | undefined,
  moduleGroupTree: Group[] | undefined,
  roles: string[] | undefined,
  pathname?: string | null,
): Group[] {
  const moduleTree = moduleGroupTree || [];
  if (hasModulePrivilege(roles, pathname) && moduleTree.length > 0) {
    return moduleTree;
  }
  return groupTree || [];
}

// Display names only: hasAuth controls selection, not whether an existing name can be shown.
export function resolveModuleGroupNameDirectory(
  flatGroups: Group[] | undefined,
  moduleGroupTree: Group[] | undefined,
  roles: string[] | undefined,
  pathname?: string | null,
): Group[] {
  if (!hasModulePrivilege(roles, pathname) || !moduleGroupTree?.length) {
    return flatGroups || [];
  }
  const directory = new Map((flatGroups || []).map((group) => [String(group.id), group]));
  const visit = (nodes: Group[]) => {
    for (const node of nodes) {
      directory.set(String(node.id), node);
      if (node.subGroups?.length) visit(node.subGroups);
    }
  };
  visit(moduleGroupTree);
  return Array.from(directory.values());
}

export function resolveOperableFlatGroups(
  flatGroups: Group[] | undefined,
  moduleGroupTree: Group[] | undefined,
  roles: string[] | undefined,
  pathname?: string | null,
): Group[] {
  if (!hasModulePrivilege(roles, pathname) || !moduleGroupTree?.length) {
    return flatGroups || [];
  }
  const groups: Group[] = [];
  const visit = (nodes: Group[]) => {
    for (const node of nodes) {
      if (node.hasAuth) groups.push(node);
      if (node.subGroups?.length) visit(node.subGroups);
    }
  };
  visit(moduleGroupTree);
  return groups;
}

export function isModuleBuiltinRole(name?: string | null): boolean {
  return name === MODULE_ADMIN_ROLE || name === MODULE_AUDITOR_ROLE;
}

export function extractModuleRoleIds(
  roleData: Array<{ children?: Array<{ id: number; name?: string; builtin?: string }> }> | undefined,
): number[] {
  const ids: number[] = [];
  for (const item of roleData || []) {
    for (const child of item.children || []) {
      if (child.builtin === 'module' || isModuleBuiltinRole(child.name)) {
        ids.push(child.id);
      }
    }
  }
  return ids;
}

export function moduleRoleDescription(
  name: string | null | undefined,
  appName: string,
  t: (key: string, fallback?: string, values?: { app: string }) => string,
): string {
  const values = { app: appName };
  if (name === MODULE_ADMIN_ROLE) {
    return t(
      'system.role.moduleAdminDesc',
      '拥有 {app} 的全部菜单和操作权限，可管理所有组织的 {app} 数据。',
      values,
    );
  }
  if (name === MODULE_AUDITOR_ROLE) {
    return t(
      'system.role.moduleAuditorDesc',
      '可查看 {app} 的全部菜单，可查看所有组织的 {app} 数据，不能修改。',
      values,
    );
  }
  return '';
}

export function moduleRoleLabel(
  name: string | null | undefined,
  t: (key: string, fallback?: string, values?: { app: string }) => string,
  appName?: string,
): string {
  if (name === MODULE_ADMIN_ROLE) {
    return appName
      ? t('system.role.moduleAdminName', '{app}管理员', { app: appName })
      : t('system.role.moduleAdmin', '模块管理员');
  }
  if (name === MODULE_AUDITOR_ROLE) {
    return appName
      ? t('system.role.moduleAuditorName', '{app}审计员', { app: appName })
      : t('system.role.moduleAuditor', '模块审计员');
  }
  return name || '';
}
