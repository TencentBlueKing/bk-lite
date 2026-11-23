import { describe, expect, it } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import {
  canSyncMonitor,
  canOpenMonitorLink,
  canOpenCmdbLink,
  builtinCmdbModelId,
  buildLinkFollowUpOffer,
  buildCmdbToMonitorFollowUp,
  buildMonitorToCmdbFollowUp,
  resolveImportFollowUpOffer,
  LINK_FOLLOW_UP_LIMIT,
  isPlatformTreeModel,
  showNodeId,
  resolveMonitorLinkMessage,
  resolveBatchPushSummaryLevel,
  pickBatchPushCounts,
  isMonitorSold,
  parseMonitorBindConflict,
  isSystemLinkAttr,
  resolveListDisplayFieldKeys,
  buildExternalIdLines,
  displayExternalIdValue,
  EXTERNAL_ID_COLUMN_KEY,
} from '@/app/cmdb/utils/systemLinkage';

describe('systemLinkage', () => {
  it('shows node id only on host', () => {
    expect(showNodeId('host')).toBe(true);
    expect(showNodeId('switch')).toBe(false);
    expect(showNodeId('mysql')).toBe(false);
  });

  it('treats node_id and monitor_id as system link attrs', () => {
    expect(isSystemLinkAttr({ attr_id: 'node_id' })).toBe(true);
    expect(isSystemLinkAttr({ attr_id: 'monitor_id' })).toBe(true);
    expect(isSystemLinkAttr({ attr_id: 'ip', is_system_link: true })).toBe(true);
    expect(isSystemLinkAttr({ attr_id: 'ip' })).toBe(false);
  });

  it('keeps the external id column out of default list fields', () => {
    const attrs = [
      { attr_id: 'inst_name' },
      { attr_id: 'ip' },
      { attr_id: 'node_id' },
      { attr_id: 'monitor_id', is_system_link: true },
    ];
    expect(resolveListDisplayFieldKeys(undefined, attrs)).toEqual(['inst_name', 'ip']);
    expect(resolveListDisplayFieldKeys(['inst_name', 'node_id', EXTERNAL_ID_COLUMN_KEY], attrs)).toEqual([
      'inst_name',
      EXTERNAL_ID_COLUMN_KEY,
    ]);
    expect(resolveListDisplayFieldKeys([], attrs)).toEqual([]);
    expect(resolveListDisplayFieldKeys(undefined, attrs)).not.toContain('inst_uuid');
    expect(resolveListDisplayFieldKeys(['inst_name', 'inst_uuid'], attrs)).toEqual([
      'inst_name',
      'inst_uuid',
    ]);
  });

  it('builds host external ids as node then monitor', () => {
    expect(buildExternalIdLines('host', {
      node_id: '  node-1  ',
      monitor_id: "('1_os_10.11.27.147',)",
    })).toEqual([
      { key: 'node_id', value: 'node-1' },
      { key: 'monitor_id', value: "('1_os_10.11.27.147',)" },
    ]);
    expect(buildExternalIdLines('switch', { node_id: 'n-1', monitor_id: 'm-1' })).toEqual([
      { key: 'monitor_id', value: 'm-1' },
    ]);
    expect(displayExternalIdValue('')).toBe('--');
    expect(displayExternalIdValue('m-1')).toBe('m-1');
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

  it('treats k8s cloud and vcenter as platform trees', () => {
    expect(isPlatformTreeModel('k8s_cluster')).toBe(true);
    expect(isPlatformTreeModel('k8s_pod')).toBe(true);
    expect(isPlatformTreeModel('vmware_vc')).toBe(true);
    expect(isPlatformTreeModel('aliyun_ecs')).toBe(true);
    expect(isPlatformTreeModel('host')).toBe(false);
    expect(isPlatformTreeModel('weblogic')).toBe(false);
    expect(isPlatformTreeModel('biz')).toBe(false);
  });

  it('hides the monitor-link entry until cmdb and monitor are both licensed', () => {
    expect(canOpenMonitorLink(undefined, false, 'host')).toBe(false);
    expect(canOpenMonitorLink([], false, 'host')).toBe(false);
    expect(canOpenMonitorLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, true, 'host')).toBe(false);
    expect(canOpenMonitorLink([{ name: 'cmdb' } as never], false, 'host')).toBe(false);
    expect(canOpenMonitorLink([{ name: 'monitor' } as never], false, 'host')).toBe(false);
    expect(canOpenMonitorLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, false, 'k8s_cluster')).toBe(false);
    expect(canOpenMonitorLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, false, 'host')).toBe(true);
    expect(canOpenMonitorLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, false, 'weblogic')).toBe(true);
  });

  it('hides the cmdb-link entry unless both apps are licensed and the object is mapped', () => {
    expect(builtinCmdbModelId('Host')).toBe('host');
    expect(builtinCmdbModelId('Weblogic')).toBeNull();
    expect(canOpenCmdbLink(undefined, false, 'Host')).toBe(false);
    expect(canOpenCmdbLink([], false, 'Host')).toBe(false);
    expect(canOpenCmdbLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, true, 'Host')).toBe(false);
    expect(canOpenCmdbLink([{ name: 'cmdb' } as never], false, 'Host')).toBe(false);
    expect(canOpenCmdbLink([{ name: 'monitor' } as never], false, 'Host')).toBe(false);
    expect(canOpenCmdbLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, false, 'Weblogic')).toBe(false);
    expect(canOpenCmdbLink([{ name: 'cmdb' }, { name: 'monitor' }] as never, false, 'Host')).toBe(true);
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

  it('parses occupied bind conflict from HandledRequestError payload', () => {
    const error = new HandledRequestError('监控实例已被其他配置项占用', {
      status: 409,
      payload: {
        result: false,
        message: '监控实例已被其他配置项占用',
        data: {
          status: 'occupied',
          occupied_inst_name: 'occupied-host',
          occupied_inst_uuid: 'uuid-1',
        },
      },
    });
    expect(parseMonitorBindConflict(error)).toEqual({
      status: 'occupied',
      occupiedLabel: 'occupied-host',
    });
  });

  it('falls back to occupied_inst_uuid when name is missing', () => {
    const error = new HandledRequestError('监控实例已被其他配置项占用', {
      status: 409,
      payload: {
        result: false,
        data: {
          status: 'occupied',
          occupied_inst_name: '  ',
          occupied_inst_uuid: 'uuid-2',
        },
      },
    });
    expect(parseMonitorBindConflict(error)).toEqual({
      status: 'occupied',
      occupiedLabel: 'uuid-2',
    });
  });

  it('treats confirm_required 409 as need-confirm without occupier', () => {
    const error = new HandledRequestError('已关联其他监控实例，确认后将先解绑再绑定', {
      status: 409,
      payload: {
        result: false,
        data: { status: 'confirm_required', monitor_id: 'm-old' },
      },
    });
    expect(parseMonitorBindConflict(error)).toEqual({
      status: 'confirm_required',
      occupiedLabel: undefined,
    });
    expect(parseMonitorBindConflict(new Error('plain'))).toEqual({});
  });

  it('builds a follow-up offer from unique ids and caps at 100', () => {
    expect(buildLinkFollowUpOffer([])).toBeNull();
    expect(buildLinkFollowUpOffer(['', '  ', null])).toBeNull();
    expect(buildLinkFollowUpOffer([' a ', 'a', 'b'])).toEqual({ ids: ['a', 'b'], overflow: 0 });
    const many = Array.from({ length: LINK_FOLLOW_UP_LIMIT + 5 }, (_, index) => `id-${index}`);
    expect(buildLinkFollowUpOffer(many)).toEqual({
      ids: many.slice(0, LINK_FOLLOW_UP_LIMIT),
      overflow: 5,
    });
    expect(buildLinkFollowUpOffer(many.slice(0, LINK_FOLLOW_UP_LIMIT), 150)).toEqual({
      ids: many.slice(0, LINK_FOLLOW_UP_LIMIT),
      overflow: 50,
    });
  });

  it('hides cmdb-to-monitor follow-up unless the list entry would show', () => {
    const licensed = [{ name: 'cmdb' }, { name: 'monitor' }] as never;
    expect(buildCmdbToMonitorFollowUp(licensed, false, 'host', ['u-1'])).toEqual({
      ids: ['u-1'],
      overflow: 0,
    });
    expect(buildCmdbToMonitorFollowUp(licensed, true, 'host', ['u-1'])).toBeNull();
    expect(buildCmdbToMonitorFollowUp(licensed, false, 'k8s_cluster', ['u-1'])).toBeNull();
    expect(buildCmdbToMonitorFollowUp([{ name: 'cmdb' }] as never, false, 'host', ['u-1'])).toBeNull();
  });

  it('hides monitor-to-cmdb follow-up unless the object is mapped and licensed', () => {
    const licensed = [{ name: 'cmdb' }, { name: 'monitor' }] as never;
    expect(buildMonitorToCmdbFollowUp(licensed, false, 'Host', ['m-1'])).toEqual({
      ids: ['m-1'],
      overflow: 0,
    });
    expect(buildMonitorToCmdbFollowUp(licensed, false, 'Weblogic', ['m-1'])).toBeNull();
    expect(buildMonitorToCmdbFollowUp(licensed, true, 'Host', ['m-1'])).toBeNull();
  });

  it('offers import follow-up only after a finished import with created uuids', () => {
    const licensed = [{ name: 'cmdb' }, { name: 'monitor' }] as never;
    const base = {
      type: 'import',
      status: 'succeeded',
      model_id: 'host',
      summary: { created: 2, created_inst_uuids: ['u-1', 'u-2'] },
    };
    expect(resolveImportFollowUpOffer({
      task: base,
      currentModelId: 'host',
      clientData: licensed,
      clientLoading: false,
    })).toEqual({ ids: ['u-1', 'u-2'], overflow: 0 });
    expect(resolveImportFollowUpOffer({
      task: { ...base, status: 'partial_success', summary: { created: 120, created_inst_uuids: ['u-1'] } },
      currentModelId: 'host',
      clientData: licensed,
      clientLoading: false,
    })).toEqual({ ids: ['u-1'], overflow: 119 });
    expect(resolveImportFollowUpOffer({
      task: { ...base, status: 'failed' },
      currentModelId: 'host',
      clientData: licensed,
      clientLoading: false,
    })).toBeNull();
    expect(resolveImportFollowUpOffer({
      task: { ...base, type: 'export' },
      currentModelId: 'host',
      clientData: licensed,
      clientLoading: false,
    })).toBeNull();
    expect(resolveImportFollowUpOffer({
      task: base,
      currentModelId: 'switch',
      clientData: licensed,
      clientLoading: false,
    })).toBeNull();
    expect(resolveImportFollowUpOffer({
      task: { ...base, summary: { created: 2 } },
      currentModelId: 'host',
      clientData: licensed,
      clientLoading: false,
    })).toBeNull();
  });
});
