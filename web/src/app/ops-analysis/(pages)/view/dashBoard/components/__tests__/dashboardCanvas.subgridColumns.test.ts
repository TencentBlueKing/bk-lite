import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const dashboardCanvasSource = readFileSync(
  fileURLToPath(new URL('../dashboardCanvas.tsx', import.meta.url)),
  'utf8',
);

test('分组子网格列数与根栅格显式对齐，禁止 auto 回落默认 12', () => {
  const rootInit = dashboardCanvasSource.match(
    /const rootGrid = GridStack\.init\(\s*\{[\s\S]*?\},\s*gridRootRef\.current,/,
  );
  const subInit = dashboardCanvasSource.match(
    /const subGrid = GridStack\.init\(\s*\{[\s\S]*?\},\s*subGridRoot,/,
  );

  assert.ok(rootInit, '必须能定位根网格 init');
  assert.ok(subInit, '必须能定位分组子网格 init');
  assert.match(
    rootInit[0],
    /column:\s*DASHBOARD_GRID_COLS/,
    '根网格必须显式使用 DASHBOARD_GRID_COLS',
  );
  assert.match(
    subInit[0],
    /column:\s*DASHBOARD_GRID_COLS/,
    '子网格必须显式使用 DASHBOARD_GRID_COLS；手动 init 写 auto 会被删掉并回落默认 12',
  );
  assert.equal(
    (subInit[0].match(/^\s*column:\s+/gm) || []).length,
    1,
    '子网格 init 只能有一处 column 配置',
  );
});
