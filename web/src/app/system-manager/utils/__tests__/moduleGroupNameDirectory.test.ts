import { describe, expect, it } from 'vitest';
import type { Group } from '@/types';
import { formatGroupNames } from '@/app/mlops/utils/common';
import { resolveModuleGroupNameDirectory, resolveOperableFlatGroups } from '@/app/system-manager/utils/moduleRoles';

const own: Group[] = [{ id: '2', name: 'Own organization' }];
const moduleTree: Group[] = [{
  id: '1', name: 'Visible ancestor', hasAuth: false,
  subGroups: [
    { id: '3', name: 'Read-only organization', hasAuth: false },
    { id: '4', name: 'External organization', hasAuth: true },
  ],
}];
const path = '/mlops/anomaly_detection/training';

describe('module organization name directory is display-only', () => {
  it('resolves nested visible names without filtering by write authorization', () => {
    const directory = resolveModuleGroupNameDirectory(own, moduleTree, ['mlops--module_admin'], path);
    expect(formatGroupNames([1, 3, 4], directory)).toBe('Visible ancestor / Read-only organization / External organization');
    expect(resolveOperableFlatGroups(own, moduleTree, ['mlops--module_admin'], path).map(group => group.id)).toEqual(['4']);
  });
  it('supports a module auditor viewing external resource names', () => {
    expect(formatGroupNames([3], resolveModuleGroupNameDirectory(own, moduleTree, ['mlops--module_auditor'], path))).toBe('Read-only organization');
  });
  it('retains previously known flat names if a populated tree omits them', () => {
    expect(formatGroupNames([2, 4], resolveModuleGroupNameDirectory(own, moduleTree, ['mlops--module_admin'], path))).toBe('Own organization / External organization');
  });
  it('preserves the original directory for ordinary and other-app roles', () => {
    expect(resolveModuleGroupNameDirectory(own, moduleTree, [], path)).toBe(own);
    expect(resolveModuleGroupNameDirectory(own, moduleTree, ['monitor--module_admin'], path)).toBe(own);
    expect(resolveModuleGroupNameDirectory(own, moduleTree, ['system-manager--module_admin'], '/system-manager/user')).toBe(own);
  });
  it('preserves the original directory while the module tree is unavailable', () => {
    expect(resolveModuleGroupNameDirectory(own, [], ['mlops--module_admin'], path)).toBe(own);
    expect(resolveModuleGroupNameDirectory(own, undefined, ['mlops--module_auditor'], path)).toBe(own);
  });
  it('does not mutate inputs or invent a label for unknown organizations', () => {
    const before = JSON.stringify({ own, moduleTree });
    expect(formatGroupNames([999], resolveModuleGroupNameDirectory(own, moduleTree, ['mlops--module_admin'], path))).toBe('--');
    expect(JSON.stringify({ own, moduleTree })).toBe(before);
  });
});
