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

  it('inserts public tabs in the spec order when the providers declared them and ids exist', () => {
    expect(
      resolveViewModalPublicTabs({
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

  it('keeps the cmdb / node tabs when only the ops-analysis key is undeclared', () => {
    // 未购运营分析 = relatedTopology 探测不到；CMDB / 节点的 Tab 不受牵连。
    expect(
      resolveViewModalPublicTabs({
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        nodeId: 'node-1',
        widgets: {
          'cmdb.baseInfo': true,
          'cmdb.assetChange': true,
          'node.nodeStatus': true,
        },
        t,
      }).map((item) => item.key),
    ).toEqual(['baseInfo', 'assetChange', 'nodeStatus']);
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

  it('looks up missing ids whenever a visible public tab could use them', () => {
    const widgets = {
      'ops-analysis.relatedTopology': true,
      'cmdb.baseInfo': true,
      'cmdb.assetChange': true,
      'node.nodeStatus': true,
    };
    expect(
      shouldLookupViewModalStableIds({
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets,
      }),
    ).toBe(true);
    // 未购运营分析只少了 relatedTopology，CMDB / 节点 Tab 仍需要补 instUuid / nodeId。
    expect(
      shouldLookupViewModalStableIds({
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets: {
          'cmdb.baseInfo': true,
          'cmdb.assetChange': true,
          'node.nodeStatus': true,
        },
      }),
    ).toBe(true);
    expect(
      shouldLookupViewModalStableIds({
        monitorId: '',
        instUuid: '',
        nodeId: '',
        widgets,
      }),
    ).toBe(false);
    expect(
      shouldLookupViewModalStableIds({
        monitorId: 'm-1',
        instUuid: '',
        nodeId: '',
        widgets: {},
      }),
    ).toBe(false);
    expect(
      shouldLookupViewModalStableIds({
        monitorId: 'm-1',
        instUuid: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        nodeId: 'node-1',
        widgets,
      }),
    ).toBe(false);
  });
});
