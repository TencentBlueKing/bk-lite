import { describe, expect, it } from 'vitest';
import {
  canSyncMonitor,
  showNodeId,
  resolveMonitorLinkMessage,
  resolveBatchPushSummaryLevel,
  pickBatchPushCounts,
  isMonitorSold,
} from '@/app/cmdb/utils/systemLinkage';

describe('systemLinkage', () => {
  it('shows node id only on host', () => {
    expect(showNodeId('host')).toBe(true);
    expect(showNodeId('switch')).toBe(false);
    expect(showNodeId('mysql')).toBe(false);
  });

  it('allows sync on mapped models', () => {
    expect(canSyncMonitor('host')).toBe(true);
    expect(canSyncMonitor('switch')).toBe(true);
    expect(canSyncMonitor('mysql')).toBe(true);
    expect(canSyncMonitor('oracle')).toBe(true);
    expect(canSyncMonitor('nginx')).toBe(true);
    expect(canSyncMonitor('docker')).toBe(true);
    expect(canSyncMonitor('k8s_cluster')).toBe(false);
    expect(canSyncMonitor('biz')).toBe(false);
  });

  it('treats empty client list as monitor sold', () => {
    expect(isMonitorSold(undefined)).toBe(true);
    expect(isMonitorSold([])).toBe(true);
    expect(isMonitorSold([{ name: 'cmdb' } as never])).toBe(false);
    expect(isMonitorSold([{ name: 'monitor' } as never])).toBe(true);
  });

  it('maps link_status to message keys', () => {
    expect(resolveMonitorLinkMessage({ link_status: 'ok' })).toBe('Model.systemLinkageSyncOk');
    expect(resolveMonitorLinkMessage({ link_status: 'not_found' })).toBe('Model.systemLinkageSyncNotFound');
    expect(resolveMonitorLinkMessage({ link_status: 'conflict' })).toBe('Model.systemLinkageSyncConflict');
  });

  it('picks batch summary counts and folds skipped_model into failed', () => {
    expect(pickBatchPushCounts({
      ok: 2,
      already_linked: 1,
      not_found: 3,
      conflict: 4,
      failed: 5,
      skipped_model: 6,
    })).toEqual({
      ok: 2,
      already_linked: 1,
      not_found: 3,
      conflict: 4,
      failed: 11,
    });
    expect(pickBatchPushCounts(undefined)).toEqual({
      ok: 0,
      already_linked: 0,
      not_found: 0,
      conflict: 0,
      failed: 0,
    });
  });

  it('maps batch summary to message level', () => {
    expect(resolveBatchPushSummaryLevel({ ok: 2, already_linked: 1 })).toBe('success');
    expect(resolveBatchPushSummaryLevel({ already_linked: 3 })).toBe('success');
    expect(resolveBatchPushSummaryLevel({ ok: 1, failed: 1 })).toBe('warning');
    expect(resolveBatchPushSummaryLevel({ ok: 1, not_found: 1, conflict: 1 })).toBe('warning');
    expect(resolveBatchPushSummaryLevel({ failed: 2 })).toBe('error');
    expect(resolveBatchPushSummaryLevel({ not_found: 1, conflict: 1 })).toBe('error');
    expect(resolveBatchPushSummaryLevel({})).toBe('error');
  });
});
