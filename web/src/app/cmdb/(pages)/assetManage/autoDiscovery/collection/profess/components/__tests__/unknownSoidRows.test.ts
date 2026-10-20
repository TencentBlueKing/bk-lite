import { describe, expect, it } from 'vitest';

import {
  canOperateUnknownSoid,
  flattenUnresolvedDevices,
  uniqueSoidRows,
  type UnresolvedDevice,
} from '../unknownSoidRows';

const devices: UnresolvedDevice[] = [
  { soid: '1.3.6.1.4.1.9', ip_addr: '10.0.0.1', mapped: true, device_type: 'switch', brand: 'Cisco', model: 'C9300' },
  { soid: '1.3.6.1.4.1.9', ip_addr: '10.0.0.2', mapped: true, device_type: 'switch', brand: 'Cisco', model: 'C9300' },
  { soid: '1.3.6.1.4.1.99999', ip_addr: '10.0.0.3', mapped: false },
];

describe('uniqueSoidRows', () => {
  it('按 SOID 合成一行并带上勾选台数', () => {
    const rows = uniqueSoidRows(devices);
    expect(rows).toEqual([
      { soid: '1.3.6.1.4.1.9', count: 2, device_type: 'switch', brand: 'Cisco', model: 'C9300', locked: true },
      { soid: '1.3.6.1.4.1.99999', count: 1, device_type: '', brand: '', model: '', locked: false },
    ]);
  });

  it('未勾选的同 SOID 设备不进入表', () => {
    const rows = uniqueSoidRows([devices[0]]);
    expect(rows).toHaveLength(1);
    expect(rows[0].count).toBe(1);
    expect(rows[0].soid).toBe('1.3.6.1.4.1.9');
  });
});

describe('flattenUnresolvedDevices', () => {
  it('把组上的映射带到每台设备', () => {
    const rows = flattenUnresolvedDevices([
      {
        soid: '1.3.6.1.4.1.9',
        mapped: true,
        device_type: 'firewall',
        brand: 'Hillstone',
        model: 'SG-6000',
        devices: [{ ip_addr: '10.0.0.8', port: '161' }],
      },
    ]);
    expect(rows[0].brand).toBe('Hillstone');
    expect(rows[0].mapped).toBe(true);
    expect(rows[0].device_type).toBe('firewall');
  });
});

describe('canOperateUnknownSoid', () => {
  it('未勾选或任务未收口时不能操作', () => {
    expect(canOperateUnknownSoid(2, 0)).toBe(false);
    expect(canOperateUnknownSoid(1, 1)).toBe(false);
    expect(canOperateUnknownSoid(0, 1)).toBe(false);
    expect(canOperateUnknownSoid(5, 1)).toBe(false);
    expect(canOperateUnknownSoid(2, 1)).toBe(true);
    expect(canOperateUnknownSoid(8, 2)).toBe(true);
  });
});
