import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import menu from '../src/app/apm/constants/menu.json';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');

type MenuRoute = {
  title?: string;
  url?: string;
  children?: readonly MenuRoute[];
};

assert.deepEqual(
  menu.zh.map(({ title }) => title),
  ['服务', '探索', '事件', '集成'],
  '中文 APM 一级菜单应将“集成”放在最右侧',
);
assert.deepEqual(
  menu.en.map(({ title }) => title),
  ['Services', 'Explore', 'Events', 'Integration'],
  '英文 APM 一级菜单应将 Integration 放在最右侧',
);

assert.deepEqual(menu.zh[1].children?.flatMap((item) => item.title ? [item.title] : []), ['调用链', '端点', '错误']);
assert.deepEqual(menu.en[1].children?.flatMap((item) => item.title ? [item.title] : []), ['Traces', 'Endpoints', 'Errors']);
assert.deepEqual(menu.zh[2].children?.flatMap((item) => item.title ? [item.title] : []), ['告警', '策略']);
assert.deepEqual(menu.en[2].children?.flatMap((item) => item.title ? [item.title] : []), ['Alerts', 'Policies']);
assert.deepEqual(menu.zh[0].children?.flatMap((item) => item.title ? [item.title] : []), ['服务', '服务拓扑', 'SLO']);
assert.deepEqual(menu.en[0].children?.flatMap((item) => item.title ? [item.title] : []), ['Services', 'Service topology', 'SLO']);
assert.deepEqual(
  menu.zh[0].children?.flatMap((item) => item.title ? [item.url] : []),
  ['/apm/services', '/apm/topology', '/apm/slo'],
  '服务一级菜单必须提供三个可深链的二级页面',
);
assert.equal(menu.zh[3].url, '/apm/integration/add', '集成一级入口必须直达添加接入页，避免客户端二次重定向');
assert.equal(menu.en[3].url, '/apm/integration/add', 'Integration must link directly to its first usable child route');
assert.equal(
  menu.zh[3].children?.some((item) => item.url === '/apm/integration' && item.isNotMenuItem),
  true,
  '集成根路由必须保留隐藏权限别名以兼容旧链接',
);
assert.doesNotMatch(
  readFileSync(join(webRoot, 'src/app/apm/integration/page.tsx'), 'utf8'),
  /\bredirect\(/,
  '集成根路由不得通过客户端导航触发 redirect，应直接渲染有效页面',
);

for (const locale of ['zh', 'en'] as const) {
  const visit = (items: readonly MenuRoute[]) => {
    for (const item of items) {
      if (item.url) {
        assert.equal(
          existsSync(join(webRoot, 'src/app', item.url, 'page.tsx')),
          true,
          `${locale} APM 菜单 ${item.title} 指向不存在的页面 ${item.url}`,
        );
      }
      if (item.children) visit(item.children);
    }
  };
  visit(menu[locale]);
}

console.log('APM menu route checks passed');
