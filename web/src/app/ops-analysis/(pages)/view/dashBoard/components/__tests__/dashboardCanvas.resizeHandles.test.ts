import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const dashboardCanvasSource = readFileSync(
  fileURLToPath(new URL('../dashboardCanvas.tsx', import.meta.url)),
  'utf8',
);

test('dashboard widgets expose four corner resize handles', () => {
  assert.match(
    dashboardCanvasSource,
    /DASHBOARD_WIDGET_RESIZE_HANDLES = 'se,sw,ne,nw'/,
    'GridStack 必须启用东南、西南、东北、西北四个角',
  );
  assert.match(
    dashboardCanvasSource,
    /resizable:\s*\{\s*handles:\s*DASHBOARD_WIDGET_RESIZE_HANDLES/,
    '根网格和分组子网格必须共用四角缩放配置',
  );
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-se \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-sw \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-nw \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-ne \{/);
});

test('dashboard still hides edge handles and group resize', () => {
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item > \.ui-resizable-n,[\s\S]*?\.ui-resizable-e,[\s\S]*?\.ui-resizable-s,[\s\S]*?\.ui-resizable-w \{[\s\S]*?display: none !important;/,
    '四边手柄必须保持隐藏，只开放四个角',
  );
  assert.doesNotMatch(
    dashboardCanvasSource,
    /\.ui-resizable-ne,[\s\S]*?\.ui-resizable-e,[\s\S]*?\.ui-resizable-s,[\s\S]*?\.ui-resizable-sw/,
    '不得再把东北、西南、西北角一并隐藏',
  );
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item\[data-node-kind='group'\] > \.ui-resizable-handle \{[\s\S]*?display: none !important;/,
    '分组容器仍不可整体缩放',
  );
});
