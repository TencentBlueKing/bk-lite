import { describe, expect, it } from 'vitest';

import {
  alarmHasAnyInstUuid,
  alarmHasAnyMonitorId,
  listAlarmSnapshotObjects,
} from '../alarmSnapshotObjects';
import { buildAlarmDetailPublicTabs } from '../alarmDetailPublicTabs';
import { resolveAlarmPublicWidgetVisibility } from '../alarmPublicWidgetVisibility';

const HOST = {
  monitor_id: 'm-1',
  cmdb_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  resource_type: 'host',
  resource_name: 'web-1',
};

const MONITOR_ONLY = {
  monitor_id: 'm-2',
  cmdb_id: null,
  resource_type: 'pod',
  resource_name: 'api-2',
};

const ASSET_ONLY = {
  monitor_id: '',
  cmdb_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  resource_type: 'switch',
  resource_name: 'sw-1',
};

const EMPTY = {
  monitor_id: '  ',
  cmdb_id: null,
  resource_type: 'unknown',
  resource_name: 'ghost',
};

describe('listAlarmSnapshotObjects', () => {
  it('lists every snapshot object including those missing one identifier', () => {
    expect(
      listAlarmSnapshotObjects([HOST, MONITOR_ONLY, ASSET_ONLY, EMPTY]),
    ).toEqual([
      {
        key: '0',
        label: 'host：web-1',
        monitorId: 'm-1',
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      },
      {
        key: '1',
        label: 'pod：api-2',
        monitorId: 'm-2',
        instUuid: '',
      },
      {
        key: '2',
        label: 'switch：sw-1',
        monitorId: '',
        instUuid: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      },
      {
        key: '3',
        label: 'unknown：ghost',
        monitorId: '',
        instUuid: '',
      },
    ]);
  });

  it('detects alarm-level identifier presence without backfilling', () => {
    expect(alarmHasAnyMonitorId([ASSET_ONLY, EMPTY])).toBe(false);
    expect(alarmHasAnyMonitorId([MONITOR_ONLY, ASSET_ONLY])).toBe(true);
    expect(alarmHasAnyInstUuid([MONITOR_ONLY, EMPTY])).toBe(false);
    expect(alarmHasAnyInstUuid([HOST])).toBe(true);
  });
});

describe('buildAlarmDetailPublicTabs', () => {
  const t = (id: string) => id;

  it('keeps the fixed order and only inserts declared public tabs when the alarm has identifiers', () => {
    expect(
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: true,
        monitorView: true,
        relatedTopology: true,
        assetInfo: true,
      }).map((tab) => tab.key),
    ).toEqual([
      'baseInfo',
      'event',
      'monitorView',
      'relatedTopology',
      'assetInfo',
      'timeline',
      'actionRecords',
    ]);
  });

  it('hides public tabs when undeclared even if identifiers exist', () => {
    expect(
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: false,
        monitorView: false,
        relatedTopology: false,
        assetInfo: false,
      }).map((tab) => tab.key),
    ).toEqual(['baseInfo', 'event', 'timeline']);
  });
});

describe('resolveAlarmPublicWidgetVisibility', () => {
  const declared = {
    monitorViewDeclared: true,
    relatedTopologyDeclared: true,
    assetInfoDeclared: true,
    hasMonitorId: true,
    hasInstUuid: true,
  };

  it('hides monitor view and asset info when ops-analysis is not sold', () => {
    expect(
      resolveAlarmPublicWidgetVisibility({
        ...declared,
        hasOpsAnalysis: false,
      }),
    ).toEqual({
      monitorView: false,
      relatedTopology: false,
      assetInfo: false,
    });
  });

  it('shows public tabs when ops-analysis is sold and identifiers exist', () => {
    expect(
      resolveAlarmPublicWidgetVisibility({
        ...declared,
        hasOpsAnalysis: true,
      }),
    ).toEqual({
      monitorView: true,
      relatedTopology: true,
      assetInfo: true,
    });
  });
});
