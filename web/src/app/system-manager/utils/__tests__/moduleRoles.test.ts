import zh from '@/app/system-manager/locales/zh.json';
import en from '@/app/system-manager/locales/en.json';
import { describe, expect, it } from 'vitest';
import { hasModulePrivilege, moduleClientIdFromPath, moduleRoleDescription, canAssignModuleRoles, extractModuleRoleIds, moduleRoleLabel } from '@/app/system-manager/utils/moduleRoles';

describe('module role path mapping', () => {
  it('maps route prefixes onto the role client id', () => {
    expect(moduleClientIdFromPath('/cmdb/assetManage')).toBe('cmdb');
    expect(moduleClientIdFromPath('/node-manager/cloudregion/node')).toBe('node');
    expect(moduleClientIdFromPath('/patch-manager/library')).toBe('patch');
  });

  it('matches the role string for that client and ignores system management', () => {
    expect(hasModulePrivilege(['node--module_admin'], '/node-manager/cloudregion')).toBe(true);
    expect(hasModulePrivilege(['node-manager--module_admin'], '/node-manager')).toBe(false);
    expect(hasModulePrivilege(['patch--module_auditor'], '/patch-manager/library')).toBe(true);
    expect(hasModulePrivilege(['system-manager--module_admin'], '/system-manager/user')).toBe(false);
    expect(hasModulePrivilege(['ops-console--module_admin'], '/ops-console/home')).toBe(false);
    expect(hasModulePrivilege(['cmdb--module_admin'], '/monitor/event')).toBe(false);
  });

  it('fills the app name into the role description', () => {
    const t = (key: string, fallback?: string, values?: { app: string }) => {
      const template = key === 'system.role.moduleAdminDesc'
        ? '拥有 {app} 的全部菜单和操作权限，可管理所有组织的 {app} 数据。'
        : fallback || key;
      return template.replaceAll('{app}', values?.app || '');
    };

    expect(moduleRoleDescription('module_admin', 'CMDB', t)).toBe(
      '拥有 CMDB 的全部菜单和操作权限，可管理所有组织的 CMDB 数据。',
    );
    expect(moduleRoleDescription('module_auditor', 'CMDB', t)).toContain('不能修改');
  });
});

describe('module role granting', () => {
  it('only allows platform superusers', () => {
    expect(canAssignModuleRoles(true)).toBe(true);
    expect(canAssignModuleRoles(false)).toBe(false);
    expect(canAssignModuleRoles(undefined)).toBe(false);
    expect(extractModuleRoleIds([{ children: [{ id: 1, name: 'module_admin' }, { id: 2, name: 'module_auditor' }, { id: 3, name: 'normal' }] }])).toEqual([1, 2]);
  });
});

describe('application-specific module role display names', () => {
  it.each([
    { messages: zh, appName: '监控中心', adminLabel: '监控中心管理员', auditorLabel: '监控中心审计员' },
    { messages: en, appName: 'Monitor Center', adminLabel: 'Monitor Center Administrator', auditorLabel: 'Monitor Center Auditor' },
  ])('uses the real locale template and app display name', ({ messages, appName, adminLabel, auditorLabel }) => {
    const t = (key: string, fallback?: string, values?: { app: string }) => {
      const template = key === 'system.role.moduleAdminName'
        ? messages.system.role.moduleAdminName
        : key === 'system.role.moduleAuditorName'
          ? messages.system.role.moduleAuditorName
          : fallback || key;
      return template.replace('{app}', values?.app || '');
    };
    expect(moduleRoleLabel('module_admin', t, appName)).toBe(adminLabel);
    expect(moduleRoleLabel('module_auditor', t, appName)).toBe(auditorLabel);
    expect(moduleRoleLabel('normal', t, appName)).toBe('normal');
  });
});
