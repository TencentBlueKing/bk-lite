import { resolveRoleTreeLabel } from '@/app/system-manager/utils/roleTreeUtils';
import { describe, expect, it } from 'vitest';
import { processRoleTreeData } from '@/app/system-manager/utils/userFormUtils';

const data = [{ id: 1, name: 'cmdb', children: [
  { id: 10, name: 'module_admin', builtin: 'module' },
  { id: 11, name: 'module_auditor', builtin: 'module' },
  { id: 12, name: 'normal' },
] }];

describe('user role tree module-role visibility', () => {
  it('hides module roles unless the platform superuser explicitly enables them', () => {
    expect(processRoleTreeData(data)[0].children?.map((node) => node.key)).toEqual([12]);
    expect(processRoleTreeData(data, 'External', false)[0].children?.map((node) => node.key)).toEqual([12]);
    expect(processRoleTreeData(data, 'External', true)[0].children?.map((node) => node.key)).toEqual([10, 11, 12]);
  });
});

it('retains parent app context from the user tree builder through the display label', () => {
  const nodes = processRoleTreeData([{ ...data[0], display_name: '资产管理', is_build_in: true }], 'External', true);
  const node = nodes[0].children?.[0];
  expect(node).toBeDefined();
  const t = (key: string, fallback?: string, values?: { app: string }) => {
    if (key === 'apps.cmdb') return 'CMDB';
    if (key === 'system.role.moduleAdminName') return `${values?.app} Administrator`;
    return fallback || key;
  };
  if (node) expect(resolveRoleTreeLabel(node, t)).toBe('CMDB Administrator');
});
