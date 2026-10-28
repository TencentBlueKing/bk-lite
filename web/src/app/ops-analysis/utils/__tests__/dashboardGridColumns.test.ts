import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';
import {
  deserializeDashboardGridStackLayout,
  serializeDashboardGridStackLayout,
} from '../dashboardGridStack';
import {
  DASHBOARD_GRID_COLS,
  migrateDashboardGridColumns,
} from '../dashboardGridColumns';

const legacyRow = (): DashboardLayoutItem[] => [
  { i: 'a', x: 0, y: 1, w: 3, h: 2, name: '甲' },
  { i: 'b', x: 3, y: 1, w: 3, h: 2, name: '乙' },
  { i: 'c', x: 6, y: 1, w: 3, h: 4, name: '丙' },
  { i: 'd', x: 9, y: 1, w: 3, h: 2, name: '丁' },
  { i: 'full', x: 0, y: 5, w: 12, h: 3, name: '满行' },
  { i: 'group', itemType: 'group', x: 0, y: 8, w: 12, h: 1, name: '分组' },
  {
    i: 'child',
    x: 3,
    y: 9,
    w: 3,
    h: 2,
    name: '子项',
    groupId: 'group',
  },
];

const boxesOverlap = (
  left: { x: number; y: number; w: number; h: number },
  right: { x: number; y: number; w: number; h: number },
) =>
  left.x < right.x + right.w
  && right.x < left.x + left.w
  && left.y < right.y + right.h
  && right.y < left.y + left.h;

test('旧盘迁移只跑一次，满行与一行四卡按 ×2 对齐且不重叠', () => {
  const once = migrateDashboardGridColumns(legacyRow(), {});
  assert.equal(once.migrated, true);
  assert.equal(once.other.gridCols, DASHBOARD_GRID_COLS);

  const byId = new Map(once.layout.map((item) => [item.i, item]));
  const full = byId.get('full');
  assert.ok(full);
  assert.equal(full.x, 0);
  assert.equal(full.w, 24);
  assert.equal(full.y, 5);
  assert.equal(full.h, 3);

  const cards = ['a', 'b', 'c', 'd'].map((id) => {
    const item = byId.get(id);
    assert.ok(item);
    return item;
  });
  assert.deepEqual(
    cards.map((item) => [item.x, item.w]),
    [[0, 6], [6, 6], [12, 6], [18, 6]],
  );
  cards.forEach((item) => {
    assert.equal(item.y, 1);
  });
  assert.equal(cards[2].h, 4);
  for (let index = 0; index < cards.length; index += 1) {
    for (let other = index + 1; other < cards.length; other += 1) {
      assert.equal(boxesOverlap(cards[index], cards[other]), false);
    }
  }
  assert.equal(cards[0].x + cards[0].w, cards[1].x);
  assert.equal(cards[3].x + cards[3].w, DASHBOARD_GRID_COLS);

  const group = byId.get('group');
  const child = byId.get('child');
  assert.ok(group && child);
  assert.equal(group.w, 24);
  assert.equal(group.h, 1);
  assert.equal(child.x, 6);
  assert.equal(child.w, 6);
  assert.equal(child.y, 9);
  assert.equal(child.h, 2);

  const twice = migrateDashboardGridColumns(once.layout, once.other);
  assert.equal(twice.migrated, false);
  assert.equal(twice.other.gridCols, 24);
  assert.deepEqual(
    twice.layout.map((item) => [item.i, item.x, item.y, item.w, item.h]),
    once.layout.map((item) => [item.i, item.x, item.y, item.w, item.h]),
  );
});

test('显式 gridCols 12 会迁移，已标记 24 不再 ×2', () => {
  const fromTwelve = migrateDashboardGridColumns(
    [{ i: 'full', x: 1, y: 2, w: 12, h: 5, name: '满行' }],
    { gridCols: 12, timeSelector: { selectValue: 15, rangePickerVaule: null } },
  );
  assert.equal(fromTwelve.migrated, true);
  assert.equal(fromTwelve.layout[0].x, 2);
  assert.equal(fromTwelve.layout[0].w, 24);
  assert.equal(fromTwelve.layout[0].y, 2);
  assert.equal(fromTwelve.layout[0].h, 5);
  assert.equal(fromTwelve.other.gridCols, 24);
  assert.equal(fromTwelve.other.timeSelector?.selectValue, 15);

  const again = migrateDashboardGridColumns(fromTwelve.layout, fromTwelve.other);
  assert.equal(again.migrated, false);
  assert.equal(again.layout[0].w, 24);
  assert.equal(again.layout[0].x, 2);

  const marked = migrateDashboardGridColumns(
    [{ i: 'full', x: 2, y: 2, w: 24, h: 5, name: '满行' }],
    { gridCols: 24 },
  );
  assert.equal(marked.migrated, false);
  assert.equal(marked.layout[0].x, 2);
  assert.equal(marked.layout[0].w, 24);
  assert.equal(marked.layout[0].y, 2);
  assert.equal(marked.layout[0].h, 5);
});

test('分组子项随 view_sets 换算一次，已标记 24 的存盘不再乘', () => {
  const stored = [
    {
      id: 'group-health',
      itemType: 'group' as const,
      x: 0,
      y: 2,
      w: 12,
      h: 4,
      headerH: 1,
      name: '主机健康',
      subGridOpts: {
        children: [
          { id: 'a', x: 0, y: 0, w: 3, h: 3, name: '甲' },
          { id: 'b', x: 3, y: 0, w: 3, h: 3, name: '乙' },
          { id: 'c', x: 6, y: 0, w: 3, h: 3, name: '丙' },
          { id: 'd', x: 9, y: 0, w: 3, h: 3, name: '丁' },
        ],
      },
    },
  ];
  const once = migrateDashboardGridColumns(deserializeDashboardGridStackLayout(stored), {});
  const saved = serializeDashboardGridStackLayout(once.layout);
  const group = saved[0];
  assert.equal(group.w, 24);
  assert.equal(group.x, 0);
  assert.equal(group.y, 2);
  assert.equal(group.headerH, 1);
  const children = group.subGridOpts?.children || [];
  assert.deepEqual(
    children.map((child) => [child.id, child.x, child.y, child.w, child.h]),
    [
      ['a', 0, 0, 6, 3],
      ['b', 6, 0, 6, 3],
      ['c', 12, 0, 6, 3],
      ['d', 18, 0, 6, 3],
    ],
  );
  children.forEach((child, index) => {
    if (index === 0) return;
    const previous = children[index - 1];
    assert.equal((previous.x || 0) + (previous.w || 0) <= (child.x || 0), true);
  });
  assert.equal((children[3].x || 0) + (children[3].w || 0), 24);

  const twice = migrateDashboardGridColumns(
    deserializeDashboardGridStackLayout(saved),
    once.other,
  );
  assert.equal(twice.migrated, false);
  assert.deepEqual(
    serializeDashboardGridStackLayout(twice.layout),
    saved,
  );
});

test('字符串 12 视为旧盘，其它列数标记不换算', () => {
  const fromText = migrateDashboardGridColumns(
    [{ i: 'card', x: 3, y: 0, w: 3, h: 2, name: '卡' }],
    { gridCols: '12' } as unknown as { gridCols: number },
  );
  assert.equal(fromText.migrated, true);
  assert.equal(fromText.layout[0].x, 6);
  assert.equal(fromText.layout[0].w, 6);
  assert.equal(fromText.other.gridCols, 24);

  const untouched = migrateDashboardGridColumns(
    [{ i: 'card', x: 3, y: 0, w: 3, h: 2, name: '卡' }],
    { gridCols: 14 },
  );
  assert.equal(untouched.migrated, false);
  assert.equal(untouched.layout[0].x, 3);
  assert.equal(untouched.layout[0].w, 3);
  assert.equal(untouched.other.gridCols, 14);
});
