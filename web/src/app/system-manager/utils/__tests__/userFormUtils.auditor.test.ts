import { describe, expect, it } from 'vitest';
import { buildUserPayload } from '../userFormUtils';

const baseForm = { lastName: 'A', locale: 'zh-Hans', zoneinfo: 'Asia/Shanghai' };

describe('buildUserPayload auditor appointment', () => {
  it('auditor payload sets is_auditor and clears roles', () => {
    const payload = buildUserPayload(baseForm, [1, 2], {}, false, true);
    expect(payload.is_auditor).toBe(true);
    expect(payload.is_superuser).toBe(false);
    expect(payload.roles).toEqual([]);
  });

  it('superuser wins when both flags are set', () => {
    const payload = buildUserPayload(baseForm, [1], {}, true, true);
    expect(payload.is_superuser).toBe(true);
    expect(payload.is_auditor).toBe(false);
  });

  it('normal user keeps personal roles', () => {
    const payload = buildUserPayload(baseForm, [9], {}, false, false);
    expect(payload.is_superuser).toBe(false);
    expect(payload.is_auditor).toBe(false);
    expect(payload.roles).toEqual([9]);
  });
});
