import { describe, expect, it } from 'vitest';
import type { Group } from '@/types/index';
import { containsAuthorizedGroup, isModuleReadOnly, resolveOperableFlatGroups } from '@/app/system-manager/utils/moduleRoles';

const own = [{ id: '2', name: 'Own organization' }] as Group[];
const moduleTree = [{
  id: '1', name: 'Ancestor', hasAuth: false,
  subGroups: [
    { id: '2', name: 'Own organization', hasAuth: true },
    { id: '3', name: 'Other organization', hasAuth: true },
  ],
}] as Group[];

describe('flat organization consumers use the current module scope', () => {
  it('includes authorized descendants, not display-only ancestors', () => {
    expect(resolveOperableFlatGroups(own, moduleTree, ['monitor--module_admin'], '/monitor/integration').map(g => g.id)).toEqual(['2', '3']);
  });

  it('also includes module auditor organizations without manufacturing groups', () => {
    expect(resolveOperableFlatGroups(own, moduleTree, ['alarm--module_auditor'], '/alarm/integration')[1]).toBe(moduleTree[0].subGroups![1]);
  });

  it('preserves ordinary and different-app flat groups exactly', () => {
    expect(resolveOperableFlatGroups(own, moduleTree, [], '/alarm/integration')).toBe(own);
    expect(resolveOperableFlatGroups(own, moduleTree, ['monitor--module_admin'], '/alarm/integration')).toBe(own);
    expect(resolveOperableFlatGroups(own, moduleTree, ['system-manager--module_admin'], '/system-manager/user')).toBe(own);
  });

  it('keeps the original fallback while the module tree is unavailable', () => {
    expect(resolveOperableFlatGroups(own, [], ['alarm--module_admin'], '/alarm/integration')).toBe(own);
  });
});

describe('module readonly write controls preserve ordinary role behavior', () => {
  it('blocks module auditor even when an ordinary app role can write', () => {
    expect(isModuleReadOnly(['alarm--module_auditor', 'alarm--admin'], '/alarm/integration')).toBe(true);
  });
  it('keeps platform auditor plus module admin readonly', () => {
    expect(isModuleReadOnly(['auditor', 'alarm--module_admin'], '/alarm/integration')).toBe(true);
  });
  it('does not restrict ordinary, other-app or platform administrator behavior', () => {
    expect(isModuleReadOnly(['alarm--admin'], '/alarm/integration')).toBe(false);
    expect(isModuleReadOnly(['job--module_auditor'], '/alarm/integration')).toBe(false);
    expect(isModuleReadOnly(['alarm--module_auditor'], '/alarm/integration', true)).toBe(false);
  });
  it('keeps the established same-app module admin precedence', () => {
    expect(isModuleReadOnly(['alarm--module_admin', 'alarm--module_auditor'], '/alarm/integration')).toBe(false);
  });
});

describe('organization fallback checks authorization, not visibility', () => {
  it('rejects a display-only ancestor while accepting its authorized child', () => {
    expect(containsAuthorizedGroup(moduleTree, '1')).toBe(false);
    expect(containsAuthorizedGroup(moduleTree, '2')).toBe(true);
  });
  it('rejects an unknown organization and an empty tree', () => {
    expect(containsAuthorizedGroup(moduleTree, '99')).toBe(false);
    expect(containsAuthorizedGroup([], '1')).toBe(false);
  });
});
