import { describe, expect, it } from 'vitest';
import {
  applyMonitorOverlay,
  canOpenAlertModal,
  mapMonitorLevelToNodeStatus,
  pickOverlayDataSourceIds,
} from '../overlayModel';

const baseNode = {
  id: 'dev-1',
  model_id: 'switch',
  name: 'SW-1',
  hop: 0,
};

describe('pickOverlayDataSourceIds', () => {
  it('returns ids when each rest_api matches exactly once', () => {
    expect(
      pickOverlayDataSourceIds([
        { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids' },
        { id: 32, rest_api: 'monitor/query_latest_active_alerts' },
        { id: 99, rest_api: 'other/query' },
      ]),
    ).toEqual({ cmdbId: 31, monitorId: 32 });
  });

  it('prefers the unique builtin when a rest_api is duplicated', () => {
    expect(
      pickOverlayDataSourceIds([
        { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: false },
        { id: 41, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: true },
        { id: 32, rest_api: 'monitor/query_latest_active_alerts' },
      ]),
    ).toEqual({ cmdbId: 41, monitorId: 32 });
  });

  it('omits a rest_api when duplicates have no unique builtin', () => {
    expect(
      pickOverlayDataSourceIds([
        { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: false },
        { id: 41, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: false },
        { id: 32, rest_api: 'monitor/query_latest_active_alerts' },
      ]),
    ).toEqual({ monitorId: 32 });
  });
});

describe('mapMonitorLevelToNodeStatus', () => {
  it('maps critical / error / warning and unknown non-empty as warning', () => {
    expect(mapMonitorLevelToNodeStatus('critical', 1)).toMatchObject({
      status: 'critical',
      pulse: true,
      color: 'red',
    });
    expect(mapMonitorLevelToNodeStatus('ERROR', 1)).toMatchObject({
      status: 'error',
      pulse: false,
      color: 'red',
    });
    expect(mapMonitorLevelToNodeStatus('info', 2)).toMatchObject({
      status: 'warning',
      pulse: false,
      color: 'yellow',
    });
  });
});

describe('applyMonitorOverlay', () => {
  it('marks missing mapping, empty monitor_id, and omitted summary as unknown', () => {
    const nodes = applyMonitorOverlay({
      nodes: [
        { ...baseNode, id: 'missing' },
        { ...baseNode, id: 'empty' },
        { ...baseNode, id: 'omitted' },
      ],
      mappings: [
        { inst_uuid: 'empty', model_id: 'switch', monitor_id: '' },
        { inst_uuid: 'omitted', model_id: 'switch', monitor_id: 'mon-9' },
      ],
      summaries: [],
    });
    expect(nodes.every((node) => node.status === 'unknown')).toBe(true);
    expect(nodes.every((node) => node.alert_count === 0)).toBe(true);
    expect(nodes[0].monitor_id).toBeUndefined();
    expect(nodes[1].monitor_id).toBeUndefined();
    expect(nodes[2].monitor_id).toBe('mon-9');
  });

  it('marks mapped zero as normal and critical summary as pulsing red', () => {
    const [quiet, noisy] = applyMonitorOverlay({
      nodes: [
        { ...baseNode, id: 'quiet' },
        { ...baseNode, id: 'noisy' },
      ],
      mappings: [
        { inst_uuid: 'quiet', model_id: 'switch', monitor_id: 'mon-q' },
        { inst_uuid: 'noisy', model_id: 'switch', monitor_id: 'mon-n' },
      ],
      summaries: [
        { instance_id: 'mon-q', count: 0, max_level: null },
        { instance_id: 'mon-n', count: 12, max_level: 'critical' },
      ],
    });
    expect(quiet).toMatchObject({ status: 'normal', alert_count: 0, pulse: false, color: 'green' });
    expect(noisy).toMatchObject({ status: 'critical', alert_count: 12, pulse: true, color: 'red' });
    expect(quiet.monitor_id).toBe('mon-q');
    expect(noisy.monitor_id).toBe('mon-n');
    expect(canOpenAlertModal(quiet)).toBe(false);
    expect(canOpenAlertModal(noisy)).toBe(true);
  });
});
