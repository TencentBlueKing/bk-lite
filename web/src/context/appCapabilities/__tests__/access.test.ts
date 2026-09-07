import { describe, expect, it } from 'vitest';

import { hasAppAccess, listAuthorizedCapabilityApps } from '../access';

describe('hasAppAccess', () => {
  it('requires the app name in the authorized client list', () => {
    expect(hasAppAccess([{ name: 'monitor' }], 'alarm')).toBe(false);
    expect(hasAppAccess([{ name: 'alarm' }], 'alarm')).toBe(true);
  });

  it('treats a missing client list as no access', () => {
    expect(hasAppAccess(undefined, 'alarm')).toBe(false);
    expect(hasAppAccess([], 'alarm')).toBe(false);
  });
});

describe('listAuthorizedCapabilityApps', () => {
  it('keeps only catalog apps the user is allowed to use', () => {
    expect(
      listAuthorizedCapabilityApps(['monitor', 'alarm'], ['alarm', 'log'])
    ).toEqual(['alarm']);
  });

  it('returns nothing when the user has no catalog apps', () => {
    expect(listAuthorizedCapabilityApps(['cmdb'], ['alarm'])).toEqual([]);
  });
});
