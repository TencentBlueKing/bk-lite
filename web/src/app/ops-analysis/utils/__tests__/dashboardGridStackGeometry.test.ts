import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem } from '../../types/dashBoard';
import {
  buildDashboardGridStackStructureKey,
  deserializeDashboardGridStackLayout,
  serializeDashboardGridStackLayout,
} from '../dashboardGridStack';

const topologyWidget = {
  i: 'topology-widget',
  x: 3,
  y: 5,
  w: 8,
  h: 6,
  name: '关系拓扑',
  groupId: null,
  valueConfig: {
    chartType: 'topologyMap',
    dataSource: 90909,
  },
} satisfies DashboardLayoutItem;

test('topology widget position and size survive dashboard save/reload', () => {
  const restored = deserializeDashboardGridStackLayout(
    serializeDashboardGridStackLayout([topologyWidget]),
  );

  assert.equal(restored.length, 1);
  assert.deepEqual(
    {
      x: restored[0].x,
      y: restored[0].y,
      w: restored[0].w,
      h: restored[0].h,
    },
    { x: 3, y: 5, w: 8, h: 6 },
  );
  assert.ok('valueConfig' in restored[0]);
  assert.deepEqual(restored[0].valueConfig, topologyWidget.valueConfig);
});

test('moving or resizing a topology widget does not change dashboard structure identity', () => {
  const movedAndResized = {
    ...topologyWidget,
    x: 7,
    y: 11,
    w: 5,
    h: 4,
  } satisfies DashboardLayoutItem;

  assert.equal(
    buildDashboardGridStackStructureKey([movedAndResized]),
    buildDashboardGridStackStructureKey([topologyWidget]),
  );
  const restored = deserializeDashboardGridStackLayout(
    serializeDashboardGridStackLayout([movedAndResized]),
  );
  assert.deepEqual(
    {
      x: restored[0].x,
      y: restored[0].y,
      w: restored[0].w,
      h: restored[0].h,
    },
    { x: 7, y: 11, w: 5, h: 4 },
  );
});

test('grouped topology widget geometry survives dashboard save/reload', () => {
  const groupedLayout: DashboardLayoutItem[] = [
    {
      i: 'group-a',
      itemType: 'group',
      x: 1,
      y: 2,
      w: 10,
      h: 1,
      name: '拓扑分组',
    },
    {
      ...topologyWidget,
      x: 2,
      y: 3,
      w: 7,
      h: 5,
      groupId: 'group-a',
    },
  ];

  const restored = deserializeDashboardGridStackLayout(
    serializeDashboardGridStackLayout(groupedLayout),
  );
  const widget = restored.find((item) => item.i === topologyWidget.i);

  assert.ok(widget);
  assert.deepEqual(
    { x: widget.x, y: widget.y, w: widget.w, h: widget.h },
    { x: 2, y: 3, w: 7, h: 5 },
  );
  assert.equal('groupId' in widget ? widget.groupId : undefined, 'group-a');
});
