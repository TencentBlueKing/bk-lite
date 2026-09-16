import { describe, expect, it } from 'vitest';

import {
  buildHostCloudQueryList,
  isCloudRegionAttr,
  parseCloudRegionId,
  toCloudSelectValue,
} from '../cloudRegion';

describe('cloudRegion', () => {
  it('parses int and numeric string cloud ids', () => {
    expect(parseCloudRegionId(1)).toBe(1);
    expect(parseCloudRegionId('2')).toBe(2);
    expect(parseCloudRegionId(' 3 ')).toBe(3);
    expect(parseCloudRegionId('')).toBeNull();
    expect(parseCloudRegionId('aliyun')).toBeNull();
  });

  it('builds host collect-task asset filters as int equality', () => {
    expect(buildHostCloudQueryList(1)).toEqual([
      { field: 'cloud', type: 'int=', value: 1 },
    ]);
    expect(buildHostCloudQueryList('2')).toEqual([
      { field: 'cloud', type: 'int=', value: 2 },
    ]);
    expect(buildHostCloudQueryList('')).toEqual([]);
  });

  it('normalizes select values for mixed stored types', () => {
    expect(toCloudSelectValue('1')).toBe(1);
    expect(toCloudSelectValue(2)).toBe(2);
    expect(toCloudSelectValue('x')).toBeUndefined();
    expect(isCloudRegionAttr('cloud')).toBe(true);
    expect(isCloudRegionAttr('cloud_id')).toBe(true);
    expect(isCloudRegionAttr('ip_addr')).toBe(false);
  });
});
