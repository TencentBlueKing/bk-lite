import { describe, expect, it } from 'vitest';

import { resolveCmdbPublicMenuItems } from '../cmdbPublicMenus';

describe('resolveCmdbPublicMenuItems', () => {
  it('shows monitor entries only when a single stable monitorId exists', () => {
    const withMonitor = resolveCmdbPublicMenuItems({
      modelId: 'host',
      monitorId: 'mon-1',
      nodeId: '',
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
        'monitor.monitorPolicy': true,
        'ops-analysis.relatedTopology': true,
      },
    });
    expect(withMonitor.map((item) => item.key)).toEqual([
      'monitorView',
      'alertList',
      'monitorPolicy',
    ]);

    const unlinked = resolveCmdbPublicMenuItems({
      modelId: 'host',
      monitorId: '',
      nodeId: '',
      widgets: {
        'monitor.monitorView': true,
        'monitor.alertList': true,
        'monitor.monitorPolicy': true,
        'ops-analysis.relatedTopology': true,
      },
    });
    expect(unlinked.map((item) => item.key)).toEqual([]);
  });

  it('never emits a relatedTopology sidebar item even when the widget is declared', () => {
    const items = resolveCmdbPublicMenuItems({
      modelId: 'host',
      monitorId: 'mon-1',
      nodeId: '',
      widgets: {
        'monitor.monitorView': true,
        'ops-analysis.relatedTopology': true,
      },
    });
    expect(items.map((item) => item.key)).toEqual(['monitorView']);
  });

  it('keeps monitor and node entries when ops-analysis related topology is undeclared', () => {
    expect(
      resolveCmdbPublicMenuItems({
        modelId: 'host',
        monitorId: 'mon-1',
        nodeId: 'node-1',
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
        modelId: 'server_room',
        monitorId: '',
        nodeId: '',
        widgets: {},
      }).map((item) => item.key),
    ).toEqual([]);
  });

  it('shows node status only for host with a direct nodeId', () => {
    expect(
      resolveCmdbPublicMenuItems({
        modelId: 'host',
        monitorId: '',
        nodeId: 'node-1',
        widgets: { 'node.nodeStatus': true },
      }).map((item) => item.key),
    ).toEqual(['nodeStatus']);

    expect(
      resolveCmdbPublicMenuItems({
        modelId: 'switch',
        monitorId: '',
        nodeId: 'node-1',
        widgets: { 'node.nodeStatus': true },
      }).map((item) => item.key),
    ).toEqual([]);
  });
});
