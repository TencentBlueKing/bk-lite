import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
  createDashboardWidgetHostRegistry,
  getOrCreateDashboardWidgetHost,
  prepareDashboardWidgetHosts,
} from '../src/app/ops-analysis/utils/dashboardWidgetHosts';

const registry = createDashboardWidgetHostRegistry<{ id: string }>();
assert.equal(
  prepareDashboardWidgetHosts(registry, 'dashboard-a', ['existing-widget']),
  false,
);
const existingHost = getOrCreateDashboardWidgetHost(
  registry,
  'existing-widget',
  () => ({ id: 'host-a' }),
);

assert.equal(
  prepareDashboardWidgetHosts(
    registry,
    'dashboard-a',
    ['existing-widget', 'new-widget'],
  ),
  true,
);
assert.equal(
  getOrCreateDashboardWidgetHost(registry, 'existing-widget', () => ({ id: 'unexpected' })),
  existingHost,
  '同一画布新增组件时必须保留旧组件的宿主身份',
);
const newHost = getOrCreateDashboardWidgetHost(
  registry,
  'new-widget',
  () => ({ id: 'host-b' }),
);
assert.equal(newHost.id, 'host-b');

prepareDashboardWidgetHosts(registry, 'dashboard-a', ['new-widget']);
assert.equal(registry.hosts.has('existing-widget'), false, '已删除组件的宿主必须被清理');

prepareDashboardWidgetHosts(registry, 'dashboard-b', ['new-widget']);
const switchedDashboardHost = getOrCreateDashboardWidgetHost(
  registry,
  'new-widget',
  () => ({ id: 'host-c' }),
);
assert.notEqual(
  switchedDashboardHost,
  newHost,
  '切换画布后不得复用上一张画布的组件宿主',
);

const dashboardCanvasSource = readFileSync(
  fileURLToPath(
    new URL(
      '../src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx',
      import.meta.url,
    ),
  ),
  'utf8',
);

assert.match(
  dashboardCanvasSource,
  /prepareDashboardWidgetHosts/,
  '同一画布结构重建前必须准备并保留现有组件宿主',
);
assert.match(
  dashboardCanvasSource,
  /getOrCreateDashboardWidgetHost/,
  '重建组件外壳时必须复用已有 Portal 宿主',
);

console.log('ops analysis dashboard widget host tests passed');
