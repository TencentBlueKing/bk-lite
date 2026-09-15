import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const topMenu = read('src/app/(core)/components/top-menu/index.tsx');
const userInfo = read('src/app/(core)/components/top-menu/user-info/index.tsx');
const subLayoutStyle = read('src/components/sub-layout/index.module.scss');
const apmRouteShell = read('src/app/apm/components/apm-route-shell.tsx');
const globalsCss = read('src/styles/globals.css');
const policyList = read('src/app/apm/events/policies/page.tsx');

assert.match(
  topMenu,
  /h-\[104px\][^"\n]*sm:h-\[56px\]/,
  '窄屏顶部导航必须使用两行高度，避免主导航与品牌和用户区重叠',
);
assert.match(
  topMenu,
  /bottom-0[^"\n]*sm:top-1\/2[^"\n]*sm:-translate-y-1\/2/,
  '窄屏主导航必须落在第二行，桌面端才居中覆盖',
);
assert.match(
  topMenu,
  /hidden font-medium sm:block/,
  '窄屏必须隐藏门户名称，为核心操作保留空间',
);
assert.match(
  userInfo,
  /hidden min-w-0 flex-col[^"\n]*sm:flex/,
  '窄屏用户入口必须隐藏可截断的文字信息，仅保留头像入口',
);

assert.match(
  topMenu,
  /absolute inset-x-0 bottom-0[^"\n]*overflow-x-hidden/,
  '全局主导航必须把横向滚动限制在视口内，不能撑宽 320px 页面',
);
assert.match(
  topMenu,
  /mx-auto flex[^"\n]*max-w-full[^"\n]*overflow-x-auto/,
  '全局主导航内容超宽时必须在自身容器内滚动',
);
assert.match(
  subLayoutStyle,
  /\.segmentedNav\s*\{[^}]*max-width:\s*100%;[^}]*overflow-x:\s*auto;/s,
  '二级分段导航必须限制在内容宽度内并允许局部滚动',
);

assert.match(
  apmRouteShell,
  /className=\{`w-full min-w-0/,
  'APM 工作区必须占满可用宽度',
);
assert.doesNotMatch(
  apmRouteShell,
  /max-w-\[1920px\]/,
  'APM 工作区不得再用 1920px 上限截断超宽屏',
);
assert.match(
  globalsCss,
  /--breakpoint-3xl:\s*120rem;/,
  '超宽屏增密必须使用统一的 3xl 断点',
);
assert.doesNotMatch(
  policyList,
  /scroll=\{\{\s*x:/,
  '策略列表不得用 scroll.x 撑出整页横滚',
);

console.log('APM responsive shell checks passed');
