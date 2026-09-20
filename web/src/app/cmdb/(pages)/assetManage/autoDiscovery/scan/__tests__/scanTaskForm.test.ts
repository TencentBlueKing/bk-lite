import { describe, expect, it } from 'vitest';

import {
  buildScanTaskSubmitMeta,
  cloudRegionFromOrigin,
  hasScanCloudRegion,
  mapScanDetailToFormValues,
  poolHasSshSecret,
  resolveAccessPointOrigin,
  resolveScanCloudRegion,
  withDefaultSnmpPool,
  withDefaultSnmpVersion,
} from '../scanTaskForm';

describe('扫描任务表单回写', () => {
  it('把详情里的超时、网段和接入点填回表单', () => {
    expect(
      mapScanDetailToFormValues({
        name: 'test',
        team: [1],
        ip_ranges: [
          { begin: '10.10.69.240', end: '10.10.69.249' },
          { begin: '10.11.27.140', end: '10.11.27.147' },
        ],
        families: ['network', 'host'],
        credentials: { host: [{ username: 'root' }] },
        access_point: [{ id: 'node-1', cloud_region_id: 1 }],
        timeout: 60,
      })
    ).toEqual({
      name: 'test',
      team: [1],
      ipRanges: [
        { begin: '10.10.69.240', end: '10.10.69.249' },
        { begin: '10.11.27.140', end: '10.11.27.147' },
      ],
      families: ['network', 'host'],
      credentials: { host: [{ username: 'root' }] },
      accessPointId: 'node-1',
      timeout: 60,
    });
  });

  it('接入点列表尚未对齐时回退到详情里的 origin', () => {
    expect(
      resolveAccessPointOrigin([], 'node-1', { id: 'node-1', cloud_region_id: 1 })
    ).toEqual({ id: 'node-1', cloud_region_id: 1 });
  });

  it('从接入点取出云区域，缺字段时保留已保存的云区域', () => {
    expect(cloudRegionFromOrigin({ cloud_region: 1, cloud_region_name: 'default' })).toEqual({
      id: 1,
      name: 'default',
    });
    expect(cloudRegionFromOrigin({ cloud_region_id: 1, cloud_region_name: 'default' })).toEqual({
      id: 1,
      name: 'default',
    });
    expect(
      resolveScanCloudRegion({
        includeCloudRegion: true,
        origin: {},
        existing: 1,
      })
    ).toBe(1);
    expect(resolveScanCloudRegion({ includeCloudRegion: false, origin: { cloud_region_id: 1 } })).toEqual({});
  });

  it('空对象或空 id 不算已填写云区域', () => {
    expect(hasScanCloudRegion({})).toBe(false);
    expect(hasScanCloudRegion({ id: undefined })).toBe(false);
    expect(hasScanCloudRegion(1)).toBe(true);
    expect(hasScanCloudRegion({ id: 1, name: 'default' })).toBe(true);
  });

  it('接入点列表尚未返回时仍提交详情里的接入点和超时', () => {
    expect(
      buildScanTaskSubmitMeta({
        accessPointId: 'node-1',
        accessPoints: [],
        fallbackAccessPoint: { id: 'node-1', cloud_region_id: 1, cloud_region_name: 'default' },
        includeCloudRegion: true,
        existingCloudRegion: 1,
        timeout: 60,
      })
    ).toEqual({
      origin: { id: 'node-1', cloud_region_id: 1, cloud_region_name: 'default' },
      access_point: [{ id: 'node-1', cloud_region_id: 1, cloud_region_name: 'default' }],
      timeout: 60,
      cloud_region: { id: 1, name: 'default' },
    });
  });

  it('PEM/私钥凭据算 SSH，不把仅密钥误判成 Agent', () => {
    expect(poolHasSshSecret([])).toBe(false);
    expect(poolHasSshSecret([{}])).toBe(false);
    expect(poolHasSshSecret([{ username: 'root', password: 'p' }])).toBe(true);
    expect(poolHasSshSecret([{ private_key: '-----BEGIN KEY-----' }])).toBe(true);
    expect(poolHasSshSecret([{ key: 'legacy-pem' }])).toBe(true);
    expect(poolHasSshSecret([{ username: '   ', password: '' }])).toBe(false);
  });

  it('SNMP 缺 version 时按界面缺省补 V2，仅用户名时补 V3', () => {
    expect(withDefaultSnmpVersion({ community: 'public' }).version).toBe('v2');
    expect(withDefaultSnmpVersion({ username: 'snmpuser' }).version).toBe('v3');
    expect(withDefaultSnmpVersion({ version: 'v2c', community: 'public' }).version).toBe('v2c');
    expect(withDefaultSnmpPool([{ community: 'public' }, { version: 'v3', username: 'u' }]).map((item) => item.version)).toEqual([
      'v2',
      'v3',
    ]);
  });

  it('回填扫描详情时给缺 version 的网络凭据补上 V2', () => {
    expect(
      mapScanDetailToFormValues({
        name: 'alltest',
        families: ['network'],
        credentials: { network: [{ community: 'public', snmp_port: '161' }] },
      }).credentials
    ).toEqual({
      network: [{ community: 'public', snmp_port: '161', version: 'v2' }],
    });
  });

  it('Agent 中间件提交云区域，SSH 中间件不强制带出', () => {
    expect(
      resolveScanCloudRegion({
        includeCloudRegion: true,
        origin: { cloud_region_id: 1, cloud_region_name: 'default' },
      })
    ).toEqual({ id: 1, name: 'default' });
    expect(
      resolveScanCloudRegion({
        includeCloudRegion: false,
        origin: { cloud_region_id: 1, cloud_region_name: 'default' },
      })
    ).toEqual({});
  });
});
