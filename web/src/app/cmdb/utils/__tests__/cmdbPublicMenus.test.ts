import { describe, expect, it } from 'vitest';

import {
  relationshipTabForPublicMenuKey,
  resolveCmdbPublicMenuItems,
} from '../cmdbPublicMenus';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

describe('resolveCmdbPublicMenuItems', () => {
  it('shows monitor entries only when a single stable monitorId exists', () => {
    const withMonitor = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'host',
      monitorId: 'mon-1',
      nodeId: '',
      isNetworkDevice: false,
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
        'monitor.monitorPolicy': true,
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(withMonitor.map((item) => item.key)).toEqual([
      'monitorView',
      'alertList',
      'monitorPolicy',
    ]);

    const unlinked = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'host',
      monitorId: '',
      nodeId: '',
      isNetworkDevice: false,
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
        'monitor.monitorPolicy': true,
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(unlinked.map((item) => item.key)).toEqual([]);
  });

  it('never emits a relatedTopology sidebar item even when the widget is declared', () => {
    const items = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'host',
      monitorId: 'mon-1',
      nodeId: '',
      isNetworkDevice: true,
      widgets: {
        'monitor.monitorView': true,
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(items.map((item) => item.key)).not.toContain('relatedTopology');
    expect(items.map((item) => item.key)).toContain('networkStatusTopology');
  });

  it('gates network status by network theme and 3D by system model only', () => {
    const network = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'switch',
      monitorId: '',
      nodeId: '',
      isNetworkDevice: true,
      widgets: {
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(network.map((item) => item.key)).toEqual(['networkStatusTopology']);
    expect(network[0]?.url).toBe(
      '/cmdb/assetData/detail/networkStatusTopology',
    );

    const system = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'system',
      monitorId: '',
      nodeId: '',
      isNetworkDevice: false,
      widgets: {
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(system.map((item) => item.key)).toEqual(['application3D']);

    const application = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'application',
      monitorId: '',
      nodeId: '',
      isNetworkDevice: false,
      widgets: {
        'ops-analysis.relatedTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(application.map((item) => item.key)).toEqual([]);
  });

  it('hides ops-analysis entries when undeclared or missing instUuid', () => {
    expect(
      resolveCmdbPublicMenuItems({
        instUuid: '',
        modelId: 'system',
        monitorId: 'mon-1',
        nodeId: '',
        isNetworkDevice: true,
        widgets: {
          'monitor.monitorView': true,
          'ops-analysis.relatedTopology': true,
          'ops-analysis.networkStatusTopology': true,
          'ops-analysis.application3D': true,
        },
      }).map((item) => item.key),
    ).toEqual(['monitorView']);

    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'system',
        monitorId: 'mon-1',
        nodeId: '',
        isNetworkDevice: true,
        widgets: {},
      }).map((item) => item.key),
    ).toEqual([]);
  });

  it('keeps monitor and node entries when only the ops-analysis keys are undeclared', () => {
    // 未购运营分析 = OA 三键探测不到；监控 / 节点入口不受牵连，不收「跨模块」税。
    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'host',
        monitorId: 'mon-1',
        nodeId: 'node-1',
        isNetworkDevice: true,
        widgets: {
          'monitor.monitorView': true,
          'monitor.alertList': true,
          'monitor.monitorPolicy': true,
          'node.nodeStatus': true,
        },
      }).map((item) => item.key),
    ).toEqual(['monitorView', 'alertList', 'monitorPolicy', 'nodeStatus']);

    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'server_room',
        monitorId: '',
        nodeId: '',
        isNetworkDevice: false,
        widgets: {},
      }).map((item) => item.key),
    ).toEqual([]);
  });

  it('shows node status only for host with a direct nodeId', () => {
    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'host',
        monitorId: '',
        nodeId: 'node-1',
        isNetworkDevice: false,
        widgets: { 'node.nodeStatus': true },
      }).map((item) => item.key),
    ).toEqual(['nodeStatus']);

    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'switch',
        monitorId: '',
        nodeId: 'node-1',
        isNetworkDevice: true,
        widgets: { 'node.nodeStatus': true },
      }).map((item) => item.key),
    ).toEqual([]);
  });

  it('puts room3D on the server room sidebar and never lets application3D stand in', () => {
    const items = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'server_room',
      monitorId: '',
      nodeId: '',
      isNetworkDevice: false,
      widgets: {
        'ops-analysis.room3D': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(items.map((item) => item.key)).toEqual(['room3D']);
    expect(items[0]?.url).toBe('/cmdb/assetData/detail/room3D');
    expect(relationshipTabForPublicMenuKey('room3D')).toBe('room3D');

    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'rack',
        monitorId: '',
        nodeId: '',
        isNetworkDevice: false,
        widgets: {
          'ops-analysis.room3D': true,
          'ops-analysis.application3D': true,
        },
      }).map((item) => item.key),
    ).toEqual([]);

    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'server_room',
        monitorId: '',
        nodeId: '',
        isNetworkDevice: false,
        widgets: { 'ops-analysis.application3D': true },
      }).map((item) => item.key),
    ).toEqual([]);
  });
});
