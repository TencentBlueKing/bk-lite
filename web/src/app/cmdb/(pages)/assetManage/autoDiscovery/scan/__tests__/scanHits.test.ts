import { describe, expect, it } from 'vitest';

import {
  countHitsByConfidence,
  DEFAULT_SCAN_CONFIDENCE_FILTER,
  filterHitsByConfidence,
  hitConfidence,
  hitHasCollectCredential,
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

  it('数据库和中间件族走同步到监控', () => {
    expect(isLinkMonitorFamilyTab('database')).toBe(true);
    expect(isLinkMonitorFamilyTab('middleware')).toBe(true);
    expect(isLinkMonitorFamilyTab('nginx')).toBe(true);
    expect(isLinkMonitorFamilyTab('mysql')).toBe(true);
    expect(isLinkMonitorFamilyTab('network')).toBe(false);
    expect(isLinkMonitorFamilyTab('host')).toBe(false);
  });
});
