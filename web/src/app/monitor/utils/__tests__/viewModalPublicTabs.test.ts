import { describe, expect, it } from 'vitest';

import {
  buildViewModalLocalTabs,
  readViewModalStableIds,
  resolveViewModalPublicTabs,
  shouldLookupViewModalStableIds,
} from '../viewModalPublicTabs';

describe('viewModal public tabs', () => {
  const t = (id: string) => id;

  it('keeps local tab keys off the public stable keys', () => {
    const localKeys = buildViewModalLocalTabs(t).map((item) => item.key);
    expect(localKeys).toEqual(['monitorView', 'alertList', 'monitorPolicy']);
    expect(localKeys).not.toContain('monitor.monitorPolicy');
    expect(localKeys).not.toContain('monitor.monitorView');
  });

  it('inserts public tabs in the spec order when ids and OA gate pass', () => {
    expect(
      resolveViewModalPublicTabs({
        hasOpsAnalysis: true,
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        nodeId: 'node-1',
        widgets: {
          'ops-analysis.relatedTopology': true,
          'cmdb.baseInfo': true,
          'cmdb.assetChange': true,
          'node.nodeStatus': true,
        },
        t,
      }),
    ).toEqual([
      {
        key: 'relatedTopology',
        identifierProp: 'instUuid',
        label: 'monitor.views.relatedTopology',
      },
      {
        key: 'baseInfo',
        identifierProp: 'instUuid',
        label: 'monitor.views.assetInfo',
      },
      {
        key: 'assetChange',
        identifierProp: 'instUuid',
        label: 'monitor.views.assetChange',
      },
      {
        key: 'nodeStatus',
        identifierProp: 'nodeId',
        label: 'monitor.views.nodeStatus',
      },
    ]);
  });

  it('hides public tabs without OA even if providers declared ids', () => {
    expect(
      resolveViewModalPublicTabs({
        hasOpsAnalysis: false,
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        nodeId: 'node-1',
        widgets: {
          'ops-analysis.relatedTopology': true,
          'cmdb.baseInfo': true,
          'cmdb.assetChange': true,
          'node.nodeStatus': true,
        },
        t,
      }),
    ).toEqual([]);
  });

  it('reads stable ids from the instance form without guessing', () => {
    expect(
      readViewModalStableIds({
        instance_id: ' m-1 ',
        cmdb_id: ' uuid-1 ',
        node_id: ' node-1 ',
      }),
    ).toEqual({
      monitorId: 'm-1',
      instUuid: 'uuid-1',
      nodeId: 'node-1',
    });
  });

  it('looks up missing ids only when OA is sold and a public tab could use them', () => {
    const widgets = {
      'ops-analysis.relatedTopology': true,
      'cmdb.baseInfo': true,
      'cmdb.assetChange': true,
      'node.nodeStatus': true,
    };
    expect(
      shouldLookupViewModalStableIds({
        hasOpsAnalysis: true,
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets,
      }),
    ).toBe(true);
    expect(
      shouldLookupViewModalStableIds({
        hasOpsAnalysis: false,
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets,
      }),
    ).toBe(false);
    expect(
      shouldLookupViewModalStableIds({
        hasOpsAnalysis: true,
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets: {},
      }),
    ).toBe(false);
    expect(
      shouldLookupViewModalStableIds({
        hasOpsAnalysis: true,
        monitorId: 'm-1',
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        nodeId: 'node-1',
        widgets,
      }),
    ).toBe(false);
  });
});
