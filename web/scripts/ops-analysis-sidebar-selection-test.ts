import assert from 'node:assert/strict';

import { resolveSidebarTreeSelection } from '../src/app/ops-analysis/utils/sidebarSelection';

assert.deepEqual(
  resolveSidebarTreeSelection({
    selectedKeys: ['dashboard_322'],
    nodeKey: 'dashboard_322',
    selected: true,
  }),
  {
    selectedKeys: ['dashboard_322'],
    navigationKey: 'dashboard_322',
  },
  '点击其他画布时应选中并导航',
);

assert.deepEqual(
  resolveSidebarTreeSelection({
    selectedKeys: [],
    nodeKey: 'dashboard_321',
    selected: false,
  }),
  {
    selectedKeys: ['dashboard_321'],
    navigationKey: null,
  },
  '重复点击当前画布时应保留选中态且不重复导航',
);

console.log('ops analysis sidebar selection tests passed');
