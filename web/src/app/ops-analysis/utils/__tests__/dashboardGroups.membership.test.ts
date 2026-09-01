import assert from 'node:assert/strict';
import test from 'node:test';

import type { DashboardLayoutItem } from '../../types/dashBoard';
import { buildDashboardGridStackStructureKey } from '../dashboardGridStack';
import {
  buildDashboardSections,
  normalizeDashboardLayoutGroupIds,
} from '../dashboardGroups';

const groupLayoutWithDraggedCoords: DashboardLayoutItem[] = [
  {
    i: 'A',
    x: 0,
    y: 0,
    w: 4,
    h: 3,
    groupId: 'G',
    name: 'Dragged A',
    valueConfig: { chartType: 'single' },
  },
  {
    i: 'B',
    x: 4,
    y: 0,
    w: 4,
    h: 3,
    groupId: 'G',
    name: 'Dragged B',
    valueConfig: { chartType: 'single' },
  },
  {
    i: 'G',
    itemType: 'group',
    x: 0,
    y: 10,
    w: 12,
    h: 1,
    name: 'Group',
  },
  {
    i: 'C',
    x: 0,
    y: 11,
    w: 4,
    h: 3,
    groupId: 'G',
    name: 'Added via menu',
    valueConfig: { chartType: 'single' },
  },
];

test('buildDashboardSections keeps widgets whose y sorts above their group', () => {
  const sections = buildDashboardSections(groupLayoutWithDraggedCoords);

  assert.deepEqual(
    sections.groups[0]?.widgets.map((item) => item.i).sort(),
    ['A', 'B', 'C'],
  );
  assert.deepEqual(sections.ungrouped.map((item) => item.i), []);
});

test('normalizeDashboardLayoutGroupIds does not strip dragged-in groupIds', () => {
  const normalized = normalizeDashboardLayoutGroupIds(groupLayoutWithDraggedCoords);

  assert.deepEqual(
    normalized
      .filter((item) => item.itemType !== 'group')
      .map((item) => ({
        i: item.i,
        groupId: 'groupId' in item ? item.groupId : null,
      })),
    [
      { i: 'A', groupId: 'G' },
      { i: 'B', groupId: 'G' },
      { i: 'C', groupId: 'G' },
    ],
  );
});

test('changing widget group membership changes dashboard structure identity', () => {
  const group: DashboardLayoutItem = {
    i: 'G',
    itemType: 'group',
    x: 0,
    y: 0,
    w: 12,
    h: 1,
    name: 'Group',
  };
  const ungroupedWidget: DashboardLayoutItem = {
    i: 'A',
    x: 0,
    y: 2,
    w: 4,
    h: 3,
    groupId: null,
    name: 'A',
    valueConfig: { chartType: 'single' },
  };
  const groupedWidget: DashboardLayoutItem = {
    i: 'A',
    x: 0,
    y: 1,
    w: 4,
    h: 3,
    groupId: 'G',
    name: 'A',
    valueConfig: { chartType: 'single' },
  };

  assert.notEqual(
    buildDashboardGridStackStructureKey([group, ungroupedWidget]),
    buildDashboardGridStackStructureKey([group, groupedWidget]),
  );
});
