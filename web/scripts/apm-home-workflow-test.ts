import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const homePage = readFileSync(join(webRoot, 'src/app/apm/page.tsx'), 'utf8');
const apiIndex = readFileSync(join(webRoot, 'src/app/apm/api/index.ts'), 'utf8');

assert.doesNotMatch(homePage, /\bredirect\(/, 'APM 首页不得重定向到其他路由');
assert.match(homePage, /getDashboard/, 'APM 首页必须调用 getDashboard');
assert.match(apiIndex, /const getDashboard = useCallback/, 'APM API 必须导出 getDashboard(window)');
assert.match(apiIndex, /\/apm\/dashboard\//, 'getDashboard 必须请求 /apm/dashboard/');
assert.match(homePage, /还没有接入任何应用/, 'APM 首页必须展示空态文案');
assert.match(homePage, /\/apm\/integration\/add/, '空态 CTA 必须指向集成添加页');
assert.match(homePage, /近 7 天无发布/, '版本发布段必须展示 P0 空态文案');
assert.match(homePage, /加载失败，点击重试/, '失败分段必须提供整页重试入口');
assert.match(homePage, /Segmented/, '首页工具栏必须提供时间窗 Segmented');
assert.doesNotMatch(homePage, /ApmRouteShell/, '首页不得使用 ApmRouteShell 页头');
assert.match(homePage, /\/apm\/events\?service=/, '告警行必须下钻到事件页并携带服务筛选');

const top5Chart = readFileSync(join(webRoot, 'src/app/apm/components/home/top5-bar-chart.tsx'), 'utf8');
assert.match(top5Chart, /\/apm\/services\/\$\{row\.service_id\}/, 'TOP5 行必须下钻到服务详情');

console.log('APM home workflow checks passed');
