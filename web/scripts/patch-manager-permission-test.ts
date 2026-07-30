import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');

const expectedMenuModules: Record<string, string> = {
  '/patch-manager/home': 'patch_dashboard',
  '/patch-manager/risk-pending': 'patch_risk',
  '/patch-manager/risk-execution': 'patch_governance',
  '/patch-manager/library': 'patch',
  '/patch-manager/baseline': 'patch_baseline',
  '/patch-manager/target': 'patch_target',
  '/patch-manager/settings': 'patch_source',
};

type MenuItem = { url?: string; name?: string; children?: MenuItem[] };
const menu = JSON.parse(read('src/app/patch-manager/constants/menu.json')) as Record<string, MenuItem[]>;

for (const [language, items] of Object.entries(menu)) {
  const flattened = items.flatMap((item) => [item, ...(item.children ?? [])]);
  for (const [url, moduleName] of Object.entries(expectedMenuModules)) {
    const item = flattened.find((candidate) => candidate.url === url);
    if (!item) throw new Error(`${language} 菜单缺少 ${url}`);
    if (item.name !== moduleName) {
      throw new Error(`${language} 菜单 ${url} 应使用 ${moduleName}，实际为 ${item.name}`);
    }
  }
}

const pagePermissions: Record<string, string[]> = {
  home: ['Add'],
  library: ['Add', 'Edit', 'Delete'],
  baseline: ['Add', 'Edit', 'Delete'],
  target: ['Add', 'Edit', 'Delete'],
  'risk-pending': ['Add'],
  'risk-execution': ['Edit'],
  settings: ['Add', 'Edit', 'Delete'],
};

for (const [page, permissions] of Object.entries(pagePermissions)) {
  const content = read(`src/app/patch-manager/(pages)/${page}/page.tsx`);
  if (!content.includes("import PermissionWrapper from '@/components/permission'")) {
    throw new Error(`${page} 页面未引入 PermissionWrapper`);
  }
  for (const permission of permissions) {
    if (!content.includes(`requiredPermissions={['${permission}']}`)) {
      throw new Error(`${page} 页面缺少 ${permission} 操作权限包装`);
    }
  }
}

const homePage = read('src/app/patch-manager/(pages)/home/page.tsx');
if (!homePage.includes('permissionPath="/patch-manager/risk-execution"')) {
  throw new Error('首页立即评估应检查执行记录模块的 Add 权限');
}
if (homePage.includes('<Spin size="large" />')) {
  throw new Error('首页居中加载指示器应与表格使用相同的默认尺寸');
}

console.log('补丁管理菜单与按钮权限约束通过');
