import { describe, expect, it } from 'vitest';
import {
  type FormFieldDependency,
  isDependencySatisfied
} from '../formFieldDependency';

const authDependency: FormFieldDependency = {
  field: ['version', 'sec_level'],
  conditions: [[{ equals: 3 }], [{ in: ['authNoPriv', 'authPriv'] }]]
};

const privDependency: FormFieldDependency = {
  field: ['version', 'sec_level'],
  conditions: [[{ equals: 3 }], [{ equals: 'authPriv' }]]
};

const isVisible = (dependency: FormFieldDependency, values: Record<string, unknown>) =>
  isDependencySatisfied(dependency, (field) => values[field]);

describe('SNMP form field dependencies', () => {
  it('hides SNMPv3 authentication and privacy fields for v2c', () => {
    const values = { version: 2, sec_level: 'authPriv' };

    expect(isVisible(authDependency, values)).toBe(false);
    expect(isVisible(privDependency, values)).toBe(false);
  });

  it('hides authentication and privacy fields for SNMPv3 noAuthNoPriv', () => {
    const values = { version: 3, sec_level: 'noAuthNoPriv' };

    expect(isVisible(authDependency, values)).toBe(false);
    expect(isVisible(privDependency, values)).toBe(false);
  });

  it('shows authentication but not privacy fields for SNMPv3 authNoPriv', () => {
    const values = { version: 3, sec_level: 'authNoPriv' };

    expect(isVisible(authDependency, values)).toBe(true);
    expect(isVisible(privDependency, values)).toBe(false);
  });

  it('shows authentication and privacy fields for SNMPv3 authPriv', () => {
    const values = { version: 3, sec_level: 'authPriv' };

    expect(isVisible(authDependency, values)).toBe(true);
    expect(isVisible(privDependency, values)).toBe(true);
  });
});
