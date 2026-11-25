import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem } from '../../types/dashBoard';
import {
  buildDashboardGridStackLayout,
  deserializeDashboardGridStackLayout,
} from '../dashboardGridStack';
import {
  buildDashboardSections,
  separateOverlappingDashboardBlocks,
} from '../dashboardGroups';

const group = (
  id: string,
  name: string,
  y: number,
  widgetHeight: number,
): DashboardLayoutItem[] => [
  {
    i: id,
    itemType: 'group',
    x: 0,
    y,
    w: 24,
    h: 1,
    name,
  },
  {
    i: `${id}-widget`,
    x: 0,
    y: y + 1,
    w: 24,
    h: widgetHeight,
    groupId: id,
    name: `${name}内容`,
  },
];

const collapsedPackedLayout = (): DashboardLayoutItem[] => [
  ...group('research', '产研度量', 0, 8),
  ...group('open-defects', '未解决缺陷', 1, 4),
  ...group('support', 'Support 工单情况', 2, 10),
  ...group('defects', '外部缺陷一眼看完', 3, 4),
];

const groupOrder = (items: DashboardLayoutItem[]) =>
  buildDashboardSections(items).groups.map((section) => section.group.name);

test('collapsed reorder keeps Support in place once groups use their full height', () => {
  const restored = separateOverlappingDashboardBlocks(collapsedPackedLayout());

  assert.deepEqual(groupOrder(restored), [
    '产研度量',
    '未解决缺陷',
    'Support 工单情况',
    '外部缺陷一眼看完',
  ]);

  const nodes = buildDashboardGridStackLayout(restored)
    .groupNodes
    .slice()
    .sort((left, right) => left.y - right.y || left.x - right.x);

  nodes.forEach((node, index) => {
    const next = nodes[index + 1];
    if (!next) {
      return;
    }
    assert.ok(
      node.y + node.h <= next.y,
      `${node.item.name} overlaps ${next.item.name}`,
    );
  });
  assert.equal(nodes[2]?.item.name, 'Support 工单情况');
  assert.notEqual(nodes.at(-1)?.item.name, 'Support 工单情况');
});

test('grid save from a collapsed drag deserializes to the same expanded order', () => {
  const stored = [
    {
      id: 'research',
      x: 0,
      y: 0,
      w: 24,
      h: 1,
      itemType: 'group',
      headerH: 1,
      name: '产研度量',
      subGridOpts: {
        children: [{ id: 'research-widget', x: 0, y: 0, w: 24, h: 8, itemType: 'widget', name: '产研内容' }],
      },
    },
    {
      id: 'open-defects',
      x: 0,
      y: 1,
      w: 24,
      h: 1,
      itemType: 'group',
      headerH: 1,
      name: '未解决缺陷',
      subGridOpts: {
        children: [{ id: 'open-widget', x: 0, y: 0, w: 24, h: 4, itemType: 'widget', name: '缺陷内容' }],
      },
    },
    {
      id: 'support',
      x: 0,
      y: 2,
      w: 24,
      h: 1,
      itemType: 'group',
      headerH: 1,
      name: 'Support 工单情况',
      subGridOpts: {
        children: [{ id: 'support-widget', x: 0, y: 0, w: 24, h: 10, itemType: 'widget', name: '工单内容' }],
      },
    },
    {
      id: 'defects',
      x: 0,
      y: 3,
      w: 24,
      h: 1,
      itemType: 'group',
      headerH: 1,
      name: '外部缺陷一眼看完',
      subGridOpts: {
        children: [{ id: 'defects-widget', x: 0, y: 0, w: 24, h: 4, itemType: 'widget', name: '一眼内容' }],
      },
    },
  ];

  const restored = deserializeDashboardGridStackLayout(stored);
  const support = restored.find((item) => item.i === 'support');
  const defects = restored.find((item) => item.i === 'defects');

  assert.ok(support);
  assert.ok(defects);
  assert.ok(support.y < defects.y);
  assert.deepEqual(groupOrder(restored), [
    '产研度量',
    '未解决缺陷',
    'Support 工单情况',
    '外部缺陷一眼看完',
  ]);

  const supportWidget = restored.find((item) => item.i === 'support-widget');
  assert.equal(supportWidget && 'groupId' in supportWidget ? supportWidget.groupId : null, 'support');
  assert.equal(supportWidget?.y, support.y + support.h);
});
