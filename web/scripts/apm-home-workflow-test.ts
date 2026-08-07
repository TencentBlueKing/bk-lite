import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const homePage = readFileSync(join(webRoot, 'src/app/apm/home/page.tsx'), 'utf8');
const rootRedirect = readFileSync(join(webRoot, 'src/app/apm/page.tsx'), 'utf8');
const apiIndex = readFileSync(join(webRoot, 'src/app/apm/api/index.ts'), 'utf8');

assert.doesNotMatch(homePage, /\bredirect\(/, 'APM 首页不得重定向到其他路由');
assert.match(homePage, /getDashboard/, 'APM 首页必须调用 getDashboard');
assert.match(apiIndex, /\/apm\/dashboard\//, 'getDashboard 必须请求 /apm/dashboard/');
assert.match(homePage, /还没有接入任何应用/, 'APM 首页必须展示空态文案');
assert.match(homePage, /Segmented/, '首页工具栏必须提供时间窗 Segmented');
assert.doesNotMatch(homePage, /ApmRouteShell/, '首页不得使用 ApmRouteShell 页头');
assert.match(rootRedirect, /\/apm\/home/, 'APM 根路径必须兼容跳转到首页');
assert.match(homePage, /\/apm\/services\/slo/, '首页 SLO 入口必须指向目录化路径');
assert.match(homePage, /\/apm\/events\/alerts/, '首页告警入口必须指向目录化路径');

const top5Chart = readFileSync(join(webRoot, 'src/app/apm/components/home/top5-bar-chart.tsx'), 'utf8');
assert.match(top5Chart, /Top5BarChart/, '首页 TOP5 图表组件必须存在');

console.log('APM home workflow checks passed');
