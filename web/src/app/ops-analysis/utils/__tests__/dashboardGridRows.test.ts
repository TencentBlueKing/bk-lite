import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem, OtherConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  deserializeDashboardGridStackLayout,
  serializeDashboardGridStackLayout,
} from '../dashboardGridStack';
import {
  DASHBOARD_GRID_ROW_HEIGHT,
  LEGACY_DASHBOARD_GRID_ROW_HEIGHT,
  migrateDashboardGridLayout,
  withCurrentDashboardGrid,
} from '../dashboardGridRows';

test('旧 24 列仪表盘换算纵向单位，保留像素尺寸、配置和输入对象', () => {
  const layout: DashboardLayoutItem[] = [
    { i: 'a', x: 0, y: 0, w: 8, h: 3, name: '甲' },
    { i: 'b', x: 8, y: 3, w: 8, h: 4, name: '乙' },
  ];
  const original = structuredClone(layout);
  for (const other of [{ gridCols: 24 }, { gridCols: 24, gridRowHeight: 60 }]) {
    const result = migrateDashboardGridLayout(layout, { ...other, custom: 'preserved' });
    assert.equal(result.migrated, true);
    assert.deepEqual(result.layout.map(({ x, y, w, h }) => [x, y, w, h]), [
      [0, 0, 8, 6],
      [8, 6, 8, 8],
    ]);
    assert.equal(result.other.gridCols, 24);
    assert.equal(result.other.gridRowHeight, 30);
    assert.equal(result.other.custom, 'preserved');
    result.layout.forEach((item, index) => {
      assert.equal(item.y * DASHBOARD_GRID_ROW_HEIGHT, layout[index].y * LEGACY_DASHBOARD_GRID_ROW_HEIGHT);
      assert.equal(item.h * DASHBOARD_GRID_ROW_HEIGHT, layout[index].h * LEGACY_DASHBOARD_GRID_ROW_HEIGHT);
    });
  }
  assert.deepEqual(layout, original);
});

test('分组标题和子组件一起换算，保存重开后不重复升级', () => {
  const stored = [{
    id: 'group', itemType: 'group' as const, x: 0, y: 4, w: 24, h: 4, headerH: 1,
    subGridOpts: { children: [
      { id: 'child', x: 0, y: 0, w: 8, h: 3, name: '子组件' },
    ] },
  }];
  const upgraded = migrateDashboardGridLayout(deserializeDashboardGridStackLayout(stored), { gridCols: 24 });
  const saved = serializeDashboardGridStackLayout(upgraded.layout);
  assert.equal(saved[0].y, 8);
  assert.equal(saved[0].h, 8);
  assert.equal(saved[0].headerH, 2);
  assert.equal(saved[0].subGridOpts?.children?.[0].y, 0);
  assert.equal(saved[0].subGridOpts?.children?.[0].h, 6);
  const reopened = migrateDashboardGridLayout(deserializeDashboardGridStackLayout(saved), upgraded.other);
  assert.equal(reopened.migrated, false);
  assert.deepEqual(serializeDashboardGridStackLayout(reopened.layout), saved);
});

test('30px 仪表盘保留奇数高度，旧列数与行高独立迁移', () => {
  const layout: DashboardLayoutItem[] = [{ i: 'a', x: 1, y: 3, w: 3, h: 7, name: '卡' }];
  for (const gridRowHeight of [30, '30']) {
    const result = migrateDashboardGridLayout(layout, { gridCols: 24, gridRowHeight } as OtherConfig);
    assert.equal(result.migrated, false);
    assert.deepEqual(result.layout, layout);
  }
  const columnsOnly = migrateDashboardGridLayout(layout, { gridCols: 12, gridRowHeight: 30 });
  assert.deepEqual(columnsOnly.layout.map(({ x, y, w, h }) => [x, y, w, h]), [[2, 3, 6, 7]]);
  const both = migrateDashboardGridLayout(layout, {});
  assert.deepEqual(both.layout.map(({ x, y, w, h }) => [x, y, w, h]), [[2, 6, 6, 14]]);
});

test('新建和保存的布局写入当前规格，并保留其他配置', () => {
  assert.deepEqual(withCurrentDashboardGrid({ custom: true }), {
    custom: true, gridCols: 24, gridRowHeight: 30,
  });
  const empty = migrateDashboardGridLayout([], {});
  assert.deepEqual(empty.layout, []);
  assert.equal(empty.other.gridRowHeight, 30);
  assert.equal(migrateDashboardGridLayout([], empty.other).migrated, false);
});
