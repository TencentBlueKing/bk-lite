import { describe, expect, it } from 'vitest';

import { resolveCmdbPublicMenuItems } from '../cmdbPublicMenus';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

describe('resolveCmdbPublicMenuItems', () => {
  it('shows monitor entries only when a single stable monitorId exists', () => {
    const withMonitor = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'host',
      monitorId: 'mon-1',
      isNetworkDevice: false,
      hasOpsAnalysis: true,
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
        'ops-analysis.relatedTopology': true,
        'ops-analysis.networkStatusTopology': true,
        'ops-analysis.application3D': true,
      },
    });
    expect(withMonitor.map((item) => item.key)).toEqual([
      'monitorView',
      'alertList',
    ]);

    const unlinked = resolveCmdbPublicMenuItems({
      instUuid: INST_UUID,
      modelId: 'host',
      monitorId: '',
      isNetworkDevice: false,
      hasOpsAnalysis: true,
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
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
      isNetworkDevice: true,
      hasOpsAnalysis: true,
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
      isNetworkDevice: true,
      hasOpsAnalysis: true,
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
      isNetworkDevice: false,
      hasOpsAnalysis: true,
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
      isNetworkDevice: false,
      hasOpsAnalysis: true,
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
        isNetworkDevice: true,
        hasOpsAnalysis: true,
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
        isNetworkDevice: true,
        hasOpsAnalysis: true,
        widgets: {},
      }).map((item) => item.key),
    ).toEqual([]);
  });

  it('hides monitor public entries when ops-analysis is not sold', () => {
    expect(
      resolveCmdbPublicMenuItems({
        instUuid: INST_UUID,
        modelId: 'host',
        monitorId: 'mon-1',
        isNetworkDevice: true,
        hasOpsAnalysis: false,
        widgets: {
          'monitor.monitorView': true,
          'monitor.alertList': true,
          'ops-analysis.networkStatusTopology': true,
          'ops-analysis.application3D': true,
        },
      }).map((item) => item.key),
    ).toEqual([]);
  });
});
