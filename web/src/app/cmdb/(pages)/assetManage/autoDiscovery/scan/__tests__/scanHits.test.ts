import { describe, expect, it } from 'vitest';

import {
  countHitsByConfidence,
  countHitsByManaged,
  DEFAULT_SCAN_CONFIDENCE_FILTER,
  DEFAULT_SCAN_MANAGED_FILTER,
  filterHitsByConfidence,
  filterHitsByManaged,
  hitConfidence,
  hitHasCmdbInstance,
  hitHasCollectCredential,
  hitIsCmdbManaged,
  hitIsMonitorManaged,
  isLinkMonitorFamilyTab,
  isScanDatabaseType,
  isScanLinkMonitorType,
  type ScanHitItem,
} from '../scanHits';

const hit = (overrides: Partial<ScanHitItem> = {}): ScanHitItem => ({
  id: 1,
  host: '10.0.1.10',
  protocol: 'mysql',
  family_model_id: 'mysql',
  status: 'success',
  soid: '',
  cmdb_model_id: 'mysql',
  credential_id: '',
  inst_uuid: '',
  port: 3306,
  confidence: 'low',
  ...overrides,
});

describe('扫描清单辅助', () => {
  it('低可信 MySQL 命中可写 CI，无凭据不能生成采集', () => {
    const row = hit();
    expect(isScanDatabaseType(row.family_model_id)).toBe(true);
    expect(hitHasCollectCredential(row)).toBe(false);
    expect(isScanLinkMonitorType(row)).toBe(true);
  });

  it('有采集凭据的命中允许生成采集', () => {
    expect(hitHasCollectCredential(hit({ credential_id: 'cred-db' }))).toBe(true);
  });

  it('未写入 CMDB 的命中没有实例，不能同步监控', () => {
    expect(hitHasCmdbInstance(hit())).toBe(false);
    expect(hitHasCmdbInstance(hit({ inst_uuid: '  ' }))).toBe(false);
    expect(hitHasCmdbInstance(hit({ inst_uuid: 'inst-1' }))).toBe(true);
  });

  it('可信度缺省为低，并按选中档过滤', () => {
    const rows = [
      hit({ id: 1, confidence: 'low' }),
      hit({ id: 2, confidence: 'medium' }),
      hit({ id: 3, confidence: 'high' }),
      hit({ id: 4, confidence: undefined }),
    ];
    expect(hitConfidence(rows[3])).toBe('low');
    expect(countHitsByConfidence(rows)).toEqual({ high: 1, medium: 1, low: 2 });
    expect(filterHitsByConfidence(rows, DEFAULT_SCAN_CONFIDENCE_FILTER).map((item) => item.id)).toEqual([2, 3]);
    expect(filterHitsByConfidence(rows, [])).toEqual([]);
  });

  it('按 CMDB / 监控纳管组合筛选', () => {
    const rows = [
      hit({ id: 1, cmdb_managed: true, monitor_managed: true }),
      hit({ id: 2, cmdb_managed: true, monitor_managed: false }),
      hit({ id: 3, cmdb_managed: false, monitor_managed: true }),
      hit({ id: 4, cmdb_managed: false, monitor_managed: false }),
    ];
    expect(hitIsCmdbManaged(rows[0])).toBe(true);
    expect(hitIsMonitorManaged(rows[2])).toBe(true);
    expect(countHitsByManaged(rows)).toEqual({
      cmdb_managed: 2,
      cmdb_unmanaged: 2,
      monitor_managed: 2,
      monitor_unmanaged: 2,
    });
    expect(filterHitsByManaged(rows, DEFAULT_SCAN_MANAGED_FILTER).map((item) => item.id)).toEqual([1, 2, 3, 4]);
    expect(filterHitsByManaged(rows, ['cmdb_unmanaged', 'monitor_unmanaged', 'monitor_managed']).map((item) => item.id)).toEqual([
      3, 4,
    ]);
    expect(filterHitsByManaged(rows, ['cmdb_managed', 'monitor_unmanaged']).map((item) => item.id)).toEqual([2]);
    expect(filterHitsByManaged(rows, [])).toEqual([]);
  });

  it('数据库和中间件族走同步到监控', () => {
    expect(isLinkMonitorFamilyTab('database')).toBe(true);
    expect(isLinkMonitorFamilyTab('middleware')).toBe(true);
    expect(isLinkMonitorFamilyTab('nginx')).toBe(true);
    expect(isLinkMonitorFamilyTab('mysql')).toBe(true);
    expect(isLinkMonitorFamilyTab('network')).toBe(false);
    expect(isLinkMonitorFamilyTab('host')).toBe(false);
  });
});
