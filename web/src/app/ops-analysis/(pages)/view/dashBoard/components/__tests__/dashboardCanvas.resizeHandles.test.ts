import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const dashboardCanvasSource = readFileSync(
  fileURLToPath(new URL('../dashboardCanvas.tsx', import.meta.url)),
  'utf8',
);

test('dashboard widgets expose eight resize handles', () => {
  assert.match(
    dashboardCanvasSource,
    /DASHBOARD_WIDGET_RESIZE_HANDLES = 'se,sw,ne,nw,n,e,s,w'/,
    'GridStack 必须同时启用四个角和四条边',
  );
  assert.match(
    dashboardCanvasSource,
    /resizable:\s*\{\s*handles:\s*DASHBOARD_WIDGET_RESIZE_HANDLES/,
    '根网格和分组子网格必须共用八向缩放配置',
  );
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-se \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-sw \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-nw \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-ne \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-n,/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-e,/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-s \{/);
  assert.match(dashboardCanvasSource, /\.grid-stack-item > \.ui-resizable-w \{/);
  assert.match(dashboardCanvasSource, /cursor: ns-resize !important;/);
  assert.match(dashboardCanvasSource, /cursor: ew-resize !important;/);
  assert.match(
    dashboardCanvasSource,
    /DASHBOARD_EDGE_HANDLE_LINE_LENGTH = 14/,
    '边中点线段长度取 14px，略长于角点 6px 的一条臂',
  );
  assert.match(
    dashboardCanvasSource,
    /DASHBOARD_EDGE_HANDLE_LINE_THICKNESS = 1\.8/,
    '边中点线宽与角点 SVG 臂宽一致',
  );
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item > \.ui-resizable-n,\s*\.grid-stack-item > \.ui-resizable-e,\s*\.grid-stack-item > \.ui-resizable-s,\s*\.grid-stack-item > \.ui-resizable-w \{\s*background-image: none !important;\s*transform: none !important;/,
    '边中点不能再套用角点的 L 形背景和旋转',
  );
  assert.match(dashboardCanvasSource, /background: rgba\(0, 0, 0, 0\.302\);/);
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item > \.ui-resizable-n::after,\s*\.grid-stack-item > \.ui-resizable-s::after \{\s*left: 50%;\s*width: \$\{DASHBOARD_EDGE_HANDLE_LINE_LENGTH\}px;\s*height: \$\{DASHBOARD_EDGE_HANDLE_LINE_THICKNESS\}px;\s*margin-left: calc\(\$\{DASHBOARD_EDGE_HANDLE_LINE_LENGTH\}px \/ -2\);/,
    '上下边是水平短线，几何中心对齐边中点',
  );
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item > \.ui-resizable-e::after,\s*\.grid-stack-item > \.ui-resizable-w::after \{\s*top: 50%;\s*width: \$\{DASHBOARD_EDGE_HANDLE_LINE_THICKNESS\}px;\s*height: \$\{DASHBOARD_EDGE_HANDLE_LINE_LENGTH\}px;\s*margin-top: calc\(\$\{DASHBOARD_EDGE_HANDLE_LINE_LENGTH\}px \/ -2\);/,
    '左右边是垂直短线，几何中心对齐边中点',
  );
  assert.match(dashboardCanvasSource, /DASHBOARD_HIDE_NS_EDGE_CLASS/);
  assert.match(dashboardCanvasSource, /DASHBOARD_HIDE_EW_EDGE_CLASS/);
  assert.match(dashboardCanvasSource, /syncDashboardEdgeHandleVisibility/);
});

test('dashboard group handles stay hidden with the corners', () => {
  assert.match(
    dashboardCanvasSource,
    /\.grid-stack-item\[data-node-kind='group'\] > \.ui-resizable-handle \{[\s\S]*?display: none !important;/,
    '分组容器的边中点必须和四角使用同一条隐藏规则',
  );
  assert.match(
    dashboardCanvasSource,
    /noResize: node\.kind === 'group'/,
    '分组容器仍不整体缩放，高度继续由内容决定',
  );
  assert.doesNotMatch(
    dashboardCanvasSource,
    /\.grid-stack-item > \.ui-resizable-n,\s*\.grid-stack-item > \.ui-resizable-e,\s*\.grid-stack-item > \.ui-resizable-s,\s*\.grid-stack-item > \.ui-resizable-w \{\s*display: none !important;/,
    '普通组件的四边不能再整组隐藏',
  );
});
