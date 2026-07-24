import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const source = readFileSync(
  path.join(
    process.cwd(),
    'src/app/log/(pages)/analysis/dashBoard/index.tsx'
  ),
  'utf8'
);

const selectedDashboardEffect = source.match(
  /\/\/ 监听 selectedDashboard[\s\S]*?useEffect\(\(\) => \{([\s\S]*?)\n    \}, \[selectedDashboard\?\.id\]\);/
)?.[1];
assert.ok(selectedDashboardEffect, '应能定位仪表盘切换 effect');
assert.equal(
  selectedDashboardEffect.includes("message.error(t('log.search.searchError'))"),
  false,
  '仪表盘先选中时，不能把尚未完成的日志分组初始化误判为空'
);

const initData = source.match(
  /const initData = async \(\) => \{([\s\S]*?)\n    \};/
)?.[1];
assert.ok(initData, '应能定位日志分组初始化逻辑');
assert.match(
  initData,
  /if \(!ids\.length\) \{\s*message\.error\(t\('log\.search\.searchError'\)\);\s*\}/,
  '只有日志分组接口确认返回空列表后才应提示分组为空'
);

console.log('log analysis group bootstrap validation passed');
