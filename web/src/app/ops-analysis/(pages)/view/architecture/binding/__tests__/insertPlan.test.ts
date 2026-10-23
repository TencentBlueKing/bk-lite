import { describe, expect, it } from 'vitest';
import {
  architectureIconIdForModel,
  architectureIconIdFromUrl,
  assetInsertLabel,
  insertSelection,
  pickArchitectureIcon,
  planInsertTiles,
} from '../insertPlan';

describe('assetInsertLabel', () => {
  it('uses the asset name, then IP, then the unnamed fallback', () => {
    expect(assetInsertLabel({ inst_name: ' web-01 ', ip_addr: '10.0.0.1' }, '未命名')).toBe('web-01');
    expect(assetInsertLabel({ inst_name: '  ', ip_addr: '10.0.0.8' }, '未命名')).toBe('10.0.0.8');
    expect(assetInsertLabel({ inst_name: '', ip_addr: '' }, '未命名')).toBe('未命名');
  });

  it('keeps the icon name within the diagram limit', () => {
    expect(assetInsertLabel({ inst_name: 'a'.repeat(140), ip_addr: '' }, '未命名')).toHaveLength(100);
  });
});

describe('insertSelection', () => {
  it('keeps pick order and drops assets already on the diagram', () => {
    const picked = [
      { inst_uuid: 'a', inst_name: 'A' },
      { inst_uuid: 'b', inst_name: 'B' },
      { inst_uuid: 'a', inst_name: 'A again' },
      { inst_uuid: 'c', inst_name: 'C' },
    ];
    expect(insertSelection(picked, new Set(['b'])).map((hit) => hit.inst_uuid)).toEqual(['a', 'c']);
  });
});

describe('architecture icons', () => {
  it('maps a realistic icon url onto the architecture palette id', () => {
    expect(architectureIconIdFromUrl('/assets/icons-realistic/cc-host_主机.svg')).toBe('cmdb-cc-host');
    expect(architectureIconIdFromUrl('/assets/icons/cc-host_主机.svg')).toBe('cmdb-cc-host');
  });

  it('uses the model icon key when the 2.5D palette has that icon', () => {
    const palette = ['cmdb-cc-host', 'cmdb-cc-default'];
    expect(architectureIconIdForModel(
      'icons/cc-host_主机',
      '/assets/icons/cc-host_主机.svg',
      palette,
    )).toBe('cmdb-cc-host');
    expect(architectureIconIdForModel(
      'icons/cc-only-flat_扁平',
      '/assets/icons-realistic/cc-default_默认.svg',
      palette,
    )).toBe('cmdb-cc-default');
  });

  it('falls back to the default icon when the preferred one is not loaded', () => {
    expect(pickArchitectureIcon('cmdb-cc-mysql', ['cmdb-cc-host', 'cmdb-cc-default'])).toBe('cmdb-cc-default');
    expect(pickArchitectureIcon('cmdb-cc-host', ['cmdb-cc-host'])).toBe('cmdb-cc-host');
    expect(pickArchitectureIcon('cmdb-cc-mysql', ['cmdb-cc-host'])).toBe('cmdb-cc-mysql');
  });
});

describe('planInsertTiles', () => {
  it('fills a region from the front, left to right, skipping occupied tiles', () => {
    expect(planInsertTiles({
      count: 3,
      occupied: [{ x: 0, y: 0 }],
      region: { from: { x: 0, y: 0 }, to: { x: 1, y: 1 } },
      origin: { x: 9, y: 9 },
    })).toEqual([
      { x: 0, y: 1 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
    ]);
  });

  it('places icons that do not fit on rows in front of the region', () => {
    expect(planInsertTiles({
      count: 3,
      occupied: [],
      region: { from: { x: 0, y: 0 }, to: { x: 1, y: 0 } },
      origin: { x: 9, y: 9 },
    })).toEqual([
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 0, y: -1 },
    ]);
  });

  it('starts an open canvas at the viewport center and continues backward', () => {
    expect(planInsertTiles({
      count: 7,
      occupied: [{ x: 0, y: 0 }],
      region: null,
      origin: { x: 0, y: 0 },
    })).toEqual([
      { x: 1, y: -1 },
      { x: 2, y: -2 },
      { x: 3, y: -3 },
      { x: 4, y: -4 },
      { x: 5, y: -5 },
      { x: 0, y: 1 },
      { x: 1, y: 0 },
    ]);
  });
});
