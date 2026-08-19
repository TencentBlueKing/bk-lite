import { describe, expect, it } from 'vitest';
import {
  canSyncMonitor,
  showNodeId,
  resolveMonitorLinkMessage,
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
});
