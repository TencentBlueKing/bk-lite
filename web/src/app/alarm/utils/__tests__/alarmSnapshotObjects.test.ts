import { describe, expect, it } from 'vitest';

import {
  alarmHasAnyInstUuid,
  alarmHasAnyMonitorId,
  alarmHasAnyNodeId,
  listAlarmSnapshotObjects,
  listIncidentAssetOptions,
  readAlarmLogAlertId,
  readAlarmServiceId,
} from '../alarmSnapshotObjects';
import { buildAlarmDetailPublicTabs } from '../alarmDetailPublicTabs';
import { resolveAlarmPublicWidgetVisibility } from '../alarmPublicWidgetVisibility';

const HOST = {
  monitor_id: 'm-1',
  cmdb_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  node_id: 'node-1',
  resource_type: 'host',
  resource_name: 'web-1',
};

const MONITOR_ONLY = {
  monitor_id: 'm-2',
  cmdb_id: null,
  node_id: null,
  resource_type: 'pod',
  resource_name: 'api-2',
};

const ASSET_ONLY = {
  monitor_id: '',
  cmdb_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  node_id: '',
  resource_type: 'switch',
  resource_name: 'sw-1',
};

const EMPTY = {
  monitor_id: '  ',
  cmdb_id: null,
  node_id: '  ',
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
        nodeId: 'node-1',
      },
      {
        key: '1',
        label: 'pod：api-2',
        monitorId: 'm-2',
        instUuid: '',
        nodeId: '',
      },
      {
        key: '2',
        label: 'switch：sw-1',
        monitorId: '',
        instUuid: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        nodeId: '',
      },
      {
        key: '3',
        label: 'unknown：ghost',
        monitorId: '',
        instUuid: '',
        nodeId: '',
      },
    ]);
  });

  it('detects alarm-level identifier presence without backfilling', () => {
    expect(alarmHasAnyMonitorId([ASSET_ONLY, EMPTY])).toBe(false);
    expect(alarmHasAnyMonitorId([MONITOR_ONLY, ASSET_ONLY])).toBe(true);
    expect(alarmHasAnyInstUuid([MONITOR_ONLY, EMPTY])).toBe(false);
    expect(alarmHasAnyInstUuid([HOST])).toBe(true);
    expect(alarmHasAnyNodeId([MONITOR_ONLY, ASSET_ONLY])).toBe(false);
    expect(alarmHasAnyNodeId([HOST])).toBe(true);
  });
});

describe('alarm-level identity readers', () => {
  it('reads logAlertId from the dedicated pointer and never invents one', () => {
    expect(readAlarmLogAlertId({ log_alert_id: ' log-1 ' })).toBe('log-1');
    expect(
      readAlarmLogAlertId({ labels: { log_alert_id: 'log-2' } }),
    ).toBe('log-2');
    expect(readAlarmLogAlertId({ labels: { other: 'x' } })).toBe('');
    expect(readAlarmLogAlertId({})).toBe('');
  });

  it('reads serviceId only when resource_type is apm_service', () => {
    expect(
      readAlarmServiceId({
        resource_type: 'apm_service',
        resource_id: ' svc-1 ',
      }),
    ).toBe('svc-1');
    expect(
      readAlarmServiceId({
        resource_type: 'host',
        resource_id: 'svc-1',
      }),
    ).toBe('');
  });
});

describe('listIncidentAssetOptions', () => {
  it('labels each switcher option with the snapshot asset name, not the raw uuid', () => {
    expect(
      listIncidentAssetOptions([
        { monitor_objects: [HOST, MONITOR_ONLY] },
        { monitor_objects: [HOST, ASSET_ONLY] },
      ]),
    ).toEqual([
      {
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        label: 'host：web-1',
      },
      {
        instUuid: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        label: 'switch：sw-1',
      },
    ]);
  });

  it('takes the first snapshot that actually froze a name and falls back to the uuid', () => {
    expect(
      listIncidentAssetOptions([
        {
          monitor_objects: [
            {
              monitor_id: 'm-9',
              cmdb_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
              node_id: '',
              resource_type: '  ',
              resource_name: '  ',
            },
          ],
        },
        {
          monitor_objects: [
            {
              monitor_id: 'm-9',
              cmdb_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
              node_id: '',
              resource_type: '',
              resource_name: 'db-1',
            },
          ],
        },
        {
          monitor_objects: [
            {
              monitor_id: 'm-10',
              cmdb_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
              node_id: '',
              resource_type: 'host',
              resource_name: '',
            },
          ],
        },
      ]),
    ).toEqual([
      { instUuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', label: 'db-1' },
      {
        instUuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        label: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
      },
    ]);
  });
});

describe('buildAlarmDetailPublicTabs', () => {
  const t = (id: string) => id;

  it('keeps the fixed order and only inserts declared public tabs when the alarm has identifiers', () => {
    expect(
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: true,
        alertRawLog: true,
        monitorView: true,
        relatedTopology: true,
        assetInfo: true,
        assetChange: true,
        nodeStatus: true,
        serviceOverview: true,
        callChain: true,
      }).map((tab) => tab.key),
    ).toEqual([
      'baseInfo',
      'event',
      'alertRawLog',
      'monitorView',
      'relatedTopology',
      'assetInfo',
      'assetChange',
      'nodeStatus',
      'serviceOverview',
      'callChain',
      'timeline',
      'actionRecords',
    ]);
  });

  it('hides public tabs when undeclared even if identifiers exist', () => {
    expect(
      buildAlarmDetailPublicTabs(t, {
        includeActionRecords: false,
        alertRawLog: false,
        monitorView: false,
        relatedTopology: false,
        assetInfo: false,
        assetChange: false,
        nodeStatus: false,
        serviceOverview: false,
        callChain: false,
      }).map((tab) => tab.key),
    ).toEqual(['baseInfo', 'event', 'timeline']);
  });
});

describe('resolveAlarmPublicWidgetVisibility', () => {
  const declared = {
    alertRawLogDeclared: true,
    monitorViewDeclared: true,
    relatedTopologyDeclared: true,
    assetInfoDeclared: true,
    assetChangeDeclared: true,
    nodeStatusDeclared: true,
    serviceOverviewDeclared: true,
    callChainDeclared: true,
    hasLogAlertId: true,
    hasMonitorId: true,
    hasInstUuid: true,
    hasNodeId: true,
    hasServiceId: true,
  };

  it('shows public tabs when the providers declared them and identifiers exist', () => {
    expect(resolveAlarmPublicWidgetVisibility(declared)).toEqual({
      alertRawLog: true,
      monitorView: true,
      relatedTopology: true,
      assetInfo: true,
      assetChange: true,
      nodeStatus: true,
      serviceOverview: true,
      callChain: true,
    });
  });

  it('drops only the undeclared widget, never a sibling from another module', () => {
    // 未购运营分析只会让 ops-analysis.relatedTopology 变成未声明，监控 / CMDB 的 Tab 不受牵连。
    expect(
      resolveAlarmPublicWidgetVisibility({
        ...declared,
        relatedTopologyDeclared: false,
      }),
    ).toEqual({
      alertRawLog: true,
      monitorView: true,
      relatedTopology: false,
      assetInfo: true,
      assetChange: true,
      nodeStatus: true,
      serviceOverview: true,
      callChain: true,
    });
    expect(
      resolveAlarmPublicWidgetVisibility({
        ...declared,
        monitorViewDeclared: false,
      }).monitorView,
    ).toBe(false);
  });

  it('still needs the stable id even when the provider declared the widget', () => {
    expect(
      resolveAlarmPublicWidgetVisibility({ ...declared, hasMonitorId: false })
        .monitorView,
    ).toBe(false);
    expect(
      resolveAlarmPublicWidgetVisibility({ ...declared, hasInstUuid: false })
        .assetInfo,
    ).toBe(false);
  });

  it('keeps the tab when any object has an id even if the current object does not', () => {
    expect(
      resolveAlarmPublicWidgetVisibility({
        ...declared,
        hasInstUuid: true,
        hasNodeId: true,
      }).assetChange,
    ).toBe(true);
  });
});
