import * as assert from 'node:assert/strict';

import {
  buildDraggingDashboardGroupState,
  buildDashboardGroupStorageKey,
  buildDashboardSections,
  buildDashboardTopLevelBlocks,
  bumpDashboardGroupWidgetReloadVersions,
  getDashboardGroupBlockHeight,
  getDashboardGroupWidgetIds,
  getVisibleDashboardLayoutItems,
  insertDashboardWidgetIntoGroup,
  moveDashboardGroupBlock,
  normalizeDashboardLayoutGroupIds,
  removeDashboardGroupHeader,
  reorderDashboardGroupBlock,
  resolveDashboardGroupDropTargetIndex,
  syncDashboardWidgetGroupIds,
  sanitizeCollapsedGroups,
  sortDashboardLayoutItems,
} from '../src/app/ops-analysis/utils/dashboardGroups';
import {
  applyDashboardGridStackLayoutChanges,
  buildDashboardGridStackStructureKey,
  buildDashboardGridStackLayout,
  deserializeDashboardGridStackLayout,
  flattenDashboardGridStackLayout,
  serializeDashboardGridStackLayout,
} from '../src/app/ops-analysis/utils/dashboardGridStack';
import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
} from '../src/app/ops-analysis/types/dashBoard';

const layout: DashboardLayoutItem[] = [
  { i: 'widget-b', x: 4, y: 1, w: 4, h: 3, name: 'B', valueConfig: { chartType: 'single' } },
  { i: 'group-health', itemType: 'group', x: 0, y: 2, w: 12, h: 1, name: '主机健康' },
  { i: 'widget-a', x: 0, y: 1, w: 4, h: 3, name: 'A', valueConfig: { chartType: 'single' } },
  { i: 'widget-c', x: 0, y: 3, w: 4, h: 3, name: 'C', groupId: 'group-health', valueConfig: { chartType: 'line' } },
];

assert.deepEqual(sortDashboardLayoutItems(layout).map((item) => item.i), [
  'widget-a',
  'widget-b',
  'group-health',
  'widget-c',
]);

const sections = buildDashboardSections(layout);
assert.deepEqual(sections.ungrouped.map((item) => item.i), ['widget-a', 'widget-b']);
assert.equal(sections.groups[0].group.i, 'group-health');
assert.deepEqual(sections.groups[0].widgets.map((item) => item.i), ['widget-c']);

assert.equal(buildDashboardGroupStorageKey('alice', 42), 'ops-analysis:dashboard-groups:alice:42');

assert.deepEqual(
  sanitizeCollapsedGroups({ 'group-health': true, orphan: true }, new Set(['group-health'])),
  { 'group-health': true },
);

assert.deepEqual(
  getVisibleDashboardLayoutItems(layout, { 'group-health': true }).map((item) => item.i),
  ['widget-a', 'widget-b', 'group-health'],
);

assert.deepEqual(
  getVisibleDashboardLayoutItems(layout, { 'group-health': true }).map((item) => ({
    i: item.i,
    y: item.y,
  })),
  [
    { i: 'widget-a', y: 0 },
    { i: 'widget-b', y: 0 },
    { i: 'group-health', y: 3 },
  ],
);

assert.deepEqual(
  getVisibleDashboardLayoutItems(layout, {}).map((item) => item.i),
  ['widget-a', 'widget-b', 'group-health', 'widget-c'],
);

assert.equal(getDashboardGroupBlockHeight(layout, 'group-health'), 4);

assert.deepEqual(buildDraggingDashboardGroupState(layout, 'group-health'), {
  groupId: 'group-health',
  proxyHeight: 1,
  hiddenWidgetIds: ['widget-c'],
});

assert.deepEqual(
  getVisibleDashboardLayoutItems(
    layout,
    {},
    buildDraggingDashboardGroupState(layout, 'group-health'),
  ).map((item) => ({ i: item.i, h: item.h })),
  [
    { i: 'widget-a', h: 3 },
    { i: 'widget-b', h: 3 },
    { i: 'group-health', h: 1 },
  ],
);

const interleavedGroupLayout = normalizeDashboardLayoutGroupIds([
  { i: 'group-a', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: 'A' },
  { i: 'a-1', x: 0, y: 1, w: 4, h: 3, name: 'A-1', groupId: 'group-a', valueConfig: { chartType: 'single' } },
  {
    i: 'free-row-1',
    x: 0,
    y: 4,
    w: 4,
    h: 3,
    groupId: null,
    name: 'Free 1',
    valueConfig: { chartType: 'single' },
  },
  { i: 'group-b', itemType: 'group', x: 0, y: 7, w: 12, h: 1, name: 'B' },
  { i: 'b-1', x: 0, y: 8, w: 4, h: 3, name: 'B-1', groupId: 'group-b', valueConfig: { chartType: 'single' } },
  {
    i: 'free-row-2',
    x: 0,
    y: 11,
    w: 4,
    h: 3,
    groupId: null,
    name: 'Free 2',
    valueConfig: { chartType: 'single' },
  },
]);

assert.deepEqual(buildDraggingDashboardGroupState(interleavedGroupLayout, 'group-a'), {
  groupId: 'group-a',
  proxyHeight: 1,
  hiddenWidgetIds: ['a-1', 'b-1'],
});

assert.deepEqual(
  getVisibleDashboardLayoutItems(
    interleavedGroupLayout,
    {},
    buildDraggingDashboardGroupState(interleavedGroupLayout, 'group-a'),
  ).map((item) => ({ i: item.i, y: item.y })),
  [
    { i: 'group-a', y: 0 },
    { i: 'free-row-1', y: 1 },
    { i: 'group-b', y: 4 },
    { i: 'free-row-2', y: 5 },
  ],
);

assert.deepEqual(
  buildDashboardTopLevelBlocks(interleavedGroupLayout).map((block) => block.key),
  ['group-a', 'ungrouped:free-row-1', 'group-b', 'ungrouped:free-row-2'],
);

assert.equal(
  resolveDashboardGroupDropTargetIndex(
    interleavedGroupLayout,
    'group-a',
    5,
    [
      { i: 'group-a', x: 0, y: 0, w: 12, h: 1 },
      { i: 'free-row-1', x: 0, y: 1, w: 4, h: 3 },
      { i: 'group-b', x: 0, y: 4, w: 12, h: 1 },
      { i: 'free-row-2', x: 0, y: 5, w: 4, h: 3 },
    ],
  ),
  2,
);

const reorderLayout: DashboardLayoutItem[] = [
  { i: 'group-a', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: 'A' },
  { i: 'a-1', x: 0, y: 1, w: 4, h: 3, name: 'A-1', groupId: 'group-a', valueConfig: { chartType: 'single' } },
  { i: 'group-b', itemType: 'group', x: 0, y: 10, w: 12, h: 1, name: 'B' },
  { i: 'b-1', x: 0, y: 11, w: 4, h: 3, name: 'B-1', groupId: 'group-b', valueConfig: { chartType: 'single' } },
];

assert.deepEqual(
  reorderDashboardGroupBlock(reorderLayout, 'group-b', 0).map((item) => item.i),
  ['group-b', 'b-1', 'group-a', 'a-1'],
);

const reorderWithUngrouped = normalizeDashboardLayoutGroupIds([
  { i: 'u-1', x: 0, y: 0, w: 4, h: 3, name: 'U-1', valueConfig: { chartType: 'single' } },
  { i: 'u-2', x: 4, y: 0, w: 4, h: 3, name: 'U-2', valueConfig: { chartType: 'single' } },
  { i: 'group-c', itemType: 'group', x: 0, y: 4, w: 12, h: 1, name: 'C' },
  { i: 'c-1', x: 0, y: 5, w: 4, h: 3, name: 'C-1', groupId: 'group-c', valueConfig: { chartType: 'single' } },
  { i: 'c-2', x: 4, y: 5, w: 4, h: 3, name: 'C-2', groupId: 'group-c', valueConfig: { chartType: 'single' } },
]);

assert.deepEqual(
  buildDashboardTopLevelBlocks(reorderWithUngrouped).map((block) => block.key),
  ['ungrouped:u-1', 'group-c'],
);

assert.equal(
  resolveDashboardGroupDropTargetIndex(reorderWithUngrouped, 'group-c', 0),
  0,
);

assert.equal(
  resolveDashboardGroupDropTargetIndex(reorderWithUngrouped, 'group-c', 7),
  1,
);

const movedAheadOfUngrouped = reorderDashboardGroupBlock(
  reorderWithUngrouped,
  'group-c',
  0,
);

assert.deepEqual(
  getVisibleDashboardLayoutItems(movedAheadOfUngrouped, {}).map((item) => item.i),
  ['group-c', 'c-1', 'c-2', 'u-1', 'u-2'],
);

const movedSections = buildDashboardSections(movedAheadOfUngrouped);
assert.deepEqual(movedSections.groups[0].widgets.map((item) => item.i), ['c-1', 'c-2']);
assert.deepEqual(movedSections.ungrouped.map((item) => item.i), ['u-1', 'u-2']);

assert.deepEqual(getDashboardGroupWidgetIds(reorderLayout, 'group-a'), ['a-1']);

assert.deepEqual(
  bumpDashboardGroupWidgetReloadVersions(reorderLayout, 'group-a', {
    'a-1': 2,
    'b-1': 5,
  }),
  {
    'a-1': 3,
    'b-1': 5,
  },
);

assert.deepEqual(removeDashboardGroupHeader(reorderLayout, 'group-a').map((item) => item.i), [
  'a-1',
  'group-b',
  'b-1',
]);

assert.deepEqual(
  moveDashboardGroupBlock(reorderLayout, 'group-a', 6).map((item) => ({ i: item.i, y: item.y })),
  [
    { i: 'group-a', y: 6 },
    { i: 'a-1', y: 7 },
    { i: 'group-b', y: 10 },
    { i: 'b-1', y: 11 },
  ],
);

const movedWidgetIntoGroup = syncDashboardWidgetGroupIds(
  normalizeDashboardLayoutGroupIds([
    { i: 'free-1', x: 0, y: 0, w: 4, h: 3, name: 'Free 1', valueConfig: { chartType: 'single' } },
    { i: 'group-d', itemType: 'group', x: 0, y: 4, w: 12, h: 1, name: 'D' },
    { i: 'd-1', x: 0, y: 5, w: 4, h: 3, name: 'D-1', groupId: 'group-d', valueConfig: { chartType: 'single' } },
  ]),
  [
    { i: 'free-1', x: 4, y: 5, w: 4, h: 3 },
    { i: 'group-d', x: 0, y: 4, w: 12, h: 1 },
    { i: 'd-1', x: 0, y: 5, w: 4, h: 3 },
  ],
);

assert.equal(
  movedWidgetIntoGroup.find((item) => item.i === 'free-1' && 'groupId' in item)?.groupId,
  'group-d',
);

const insertedWidget: DashboardWidgetLayoutItem = {
  i: 'new-in-group',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: 'New in Group',
  groupId: null,
  valueConfig: { chartType: 'single' },
};

const insertedIntoGroup = insertDashboardWidgetIntoGroup(
  reorderWithUngrouped,
  insertedWidget,
  'group-c',
);
const insertedSections = buildDashboardSections(insertedIntoGroup);

assert.deepEqual(
  insertedSections.groups[0].widgets.map((item) => item.i),
  ['c-1', 'c-2', 'new-in-group'],
);
assert.equal(
  insertedIntoGroup.find((item) => item.i === 'new-in-group' && 'groupId' in item)?.groupId,
  'group-c',
);

const staggeredGroupLayout = normalizeDashboardLayoutGroupIds([
  { i: 'group-staggered', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: 'Staggered' },
  { i: 's-1', x: 0, y: 1, w: 4, h: 3, name: 'S-1', groupId: 'group-staggered', valueConfig: { chartType: 'single' } },
  { i: 's-2', x: 4, y: 1, w: 4, h: 6, name: 'S-2', groupId: 'group-staggered', valueConfig: { chartType: 'single' } },
  { i: 's-3', x: 8, y: 1, w: 4, h: 3, name: 'S-3', groupId: 'group-staggered', valueConfig: { chartType: 'single' } },
]);

const insertedIntoGap = insertDashboardWidgetIntoGroup(
  staggeredGroupLayout,
  {
    i: 'gap-fill',
    x: 0,
    y: 0,
    w: 4,
    h: 3,
    name: 'Gap Fill',
    groupId: null,
    valueConfig: { chartType: 'single' },
  },
  'group-staggered',
);

assert.deepEqual(
  insertedIntoGap.find((item) => item.i === 'gap-fill' && 'groupId' in item),
  {
    i: 'gap-fill',
    x: 0,
    y: 4,
    w: 4,
    h: 3,
    name: 'Gap Fill',
    groupId: 'group-staggered',
    valueConfig: { chartType: 'single' },
  },
);

const emptyGroupLayout = normalizeDashboardLayoutGroupIds([
  { i: 'ungrouped-1', x: 0, y: 0, w: 4, h: 3, name: 'Ungrouped', valueConfig: { chartType: 'single' } },
  { i: 'group-empty', itemType: 'group', x: 0, y: 4, w: 12, h: 1, name: 'Empty' },
  {
    i: 'after-empty',
    x: 0,
    y: 5,
    w: 4,
    h: 3,
    groupId: null,
    name: 'After Empty',
    valueConfig: { chartType: 'single' },
  },
]);

const draggedIntoEmptyGroup = syncDashboardWidgetGroupIds(
  emptyGroupLayout,
  [
    { i: 'ungrouped-1', x: 4, y: 5, w: 4, h: 3 },
    { i: 'group-empty', x: 0, y: 4, w: 12, h: 1 },
    { i: 'after-empty', x: 0, y: 8, w: 4, h: 3 },
  ],
  'ungrouped-1',
);

const emptyGroupSections = buildDashboardSections(draggedIntoEmptyGroup);
assert.deepEqual(
  emptyGroupSections.groups.find((section) => section.group.i === 'group-empty')?.widgets.map((item) => item.i),
  ['ungrouped-1'],
);
assert.equal(
  draggedIntoEmptyGroup.find((item) => item.i === 'ungrouped-1' && 'groupId' in item)?.y,
  5,
);
assert.equal(
  draggedIntoEmptyGroup.find((item) => item.i === 'after-empty')?.y,
  11,
);

const gridStackLayout = buildDashboardGridStackLayout(reorderWithUngrouped);

assert.deepEqual(
  gridStackLayout.topLevelNodes.map((node) => `${node.kind}:${node.id}`),
  ['widget:u-1', 'widget:u-2', 'group:group-c'],
);

assert.deepEqual(
  gridStackLayout.groupNodes[0].children.map((child) => child.id),
  ['c-1', 'c-2'],
);

const layoutWithGroupGap = normalizeDashboardLayoutGroupIds([
  { i: 'group-gap', itemType: 'group', x: 0, y: 0, w: 12, h: 1, name: 'Gap' },
  { i: 'gap-child', x: 0, y: 6, w: 4, h: 3, name: 'Gap Child', groupId: 'group-gap', valueConfig: { chartType: 'single' } },
]);

const compactedGapLayout = buildDashboardGridStackLayout(layoutWithGroupGap);
assert.deepEqual(compactedGapLayout.groupNodes[0].children.map((child) => ({
  id: child.id,
  y: child.y,
})), [{ id: 'gap-child', y: 0 }]);
assert.equal(compactedGapLayout.groupNodes[0].h, 4);

assert.equal(
  buildDashboardGridStackStructureKey(reorderWithUngrouped),
  buildDashboardGridStackStructureKey(
    reorderWithUngrouped.map((item) =>
      item.i === 'c-1'
        ? { ...item, y: item.y + 2 }
        : item,
    ),
  ),
);

assert.equal(
  buildDashboardGridStackStructureKey(reorderWithUngrouped),
  buildDashboardGridStackStructureKey(
    reorderWithUngrouped.map((item) =>
      item.i === 'c-1' && 'groupId' in item
        ? { ...item, groupId: null }
        : item,
    ),
  ),
);

assert.notEqual(
  buildDashboardGridStackStructureKey(reorderWithUngrouped),
  buildDashboardGridStackStructureKey(
    reorderWithUngrouped.filter((item) => item.i !== 'c-2'),
  ),
);

const flattenedGridStackLayout = flattenDashboardGridStackLayout(gridStackLayout);

const serializedGridStackLayout = serializeDashboardGridStackLayout(reorderWithUngrouped);

assert.deepEqual(
  serializedGridStackLayout.map((item) => item.id),
  ['u-1', 'u-2', 'group-c'],
);

assert.deepEqual(
  serializedGridStackLayout.find((item) => item.id === 'group-c')?.subGridOpts?.children?.map((item) => item.id),
  ['c-1', 'c-2'],
);

assert.deepEqual(
  deserializeDashboardGridStackLayout(serializedGridStackLayout).map((item) => item.i),
  ['u-1', 'u-2', 'group-c', 'c-1', 'c-2'],
);

const nativeOrderSourceLayout = deserializeDashboardGridStackLayout([
  {
    id: 'group-first',
    x: 0,
    y: 6,
    w: 12,
    h: 4,
    headerH: 1,
    itemType: 'group',
    name: 'Group First',
    subGridOpts: {
      children: [
        {
          id: 'group-first-child',
          x: 0,
          y: 0,
          w: 4,
          h: 3,
          itemType: 'widget',
          name: 'Child',
          valueConfig: { chartType: 'single' },
        },
      ],
    },
  },
  {
    id: 'top-widget-second',
    x: 0,
    y: 0,
    w: 4,
    h: 3,
    itemType: 'widget',
    name: 'Top Widget Second',
    valueConfig: { chartType: 'single' },
  },
]);

assert.deepEqual(
  buildDashboardGridStackLayout(nativeOrderSourceLayout).topLevelNodes.map(
    (node) => `${node.kind}:${node.id}`,
  ),
  ['group:group-first', 'widget:top-widget-second'],
);

assert.deepEqual(
  serializeDashboardGridStackLayout(nativeOrderSourceLayout).map((item) => item.id),
  ['group-first', 'top-widget-second'],
);

assert.equal(
  deserializeDashboardGridStackLayout(serializedGridStackLayout).find((item) => item.i === 'c-1' && 'groupId' in item)?.groupId,
  'group-c',
);

assert.deepEqual(
  deserializeDashboardGridStackLayout(reorderWithUngrouped).map((item) => item.i),
  ['u-1', 'u-2', 'group-c', 'c-1', 'c-2'],
);

assert.deepEqual(
  flattenedGridStackLayout.map((item) => item.i),
  ['u-1', 'u-2', 'group-c', 'c-1', 'c-2'],
);

assert.equal(
  flattenedGridStackLayout.find((item) => item.i === 'c-1' && 'groupId' in item)?.groupId,
  'group-c',
);

const gridStackChangedLayout = applyDashboardGridStackLayoutChanges(
  reorderWithUngrouped,
  [
    { id: 'u-1', x: 0, y: 0, w: 4, h: 3 },
    { id: 'u-2', x: 4, y: 0, w: 4, h: 3 },
    {
      id: 'group-c',
      x: 0,
      y: 6,
      w: 12,
      h: 1,
      children: [
        { id: 'c-1', x: 0, y: 0, w: 4, h: 3 },
        { id: 'c-2', x: 4, y: 3, w: 4, h: 3 },
      ],
    },
  ],
);

assert.equal(gridStackChangedLayout.find((item) => item.i === 'group-c')?.y, 6);
assert.equal(gridStackChangedLayout.find((item) => item.i === 'c-1')?.y, 7);
assert.equal(
  gridStackChangedLayout.find((item) => item.i === 'c-2' && 'groupId' in item)?.groupId,
  'group-c',
);

console.log('dashboard-groups validation passed');
