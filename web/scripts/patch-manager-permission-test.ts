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
  '/patch-manager/settings/sources': 'patch_source',
  '/patch-manager/settings/scan': 'patch_scan_setting',
};

type MenuItem = { url?: string; name?: string; children?: MenuItem[] };
const menu = JSON.parse(read('src/app/patch-manager/constants/menu.json')) as Record<string, MenuItem[]>;

for (const [language, items] of Object.entries(menu)) {
  const flatten = (menuItems: MenuItem[]): MenuItem[] => menuItems.flatMap((item) => [item, ...flatten(item.children ?? [])]);
  const flattened = flatten(items);
  const settings = flattened.find((candidate) => candidate.url === '/patch-manager/settings');
  if (!settings || settings.name !== 'patch_settings') {
    throw new Error(`${language} 菜单缺少设置父菜单`);
  }
  if (settings.children?.map((child) => child.url).join(',') !== '/patch-manager/settings/sources,/patch-manager/settings/scan') {
    throw new Error(`${language} 设置子菜单顺序不正确`);
  }
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
  'settings/_components/settings-content.tsx': ['Add', 'Edit', 'Delete'],
};

for (const [page, permissions] of Object.entries(pagePermissions)) {
  const pagePath = page.endsWith('.tsx')
    ? `src/app/patch-manager/(pages)/${page}`
    : `src/app/patch-manager/(pages)/${page}/page.tsx`;
  const content = read(pagePath);
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

const instancePermissionPages = ['target', 'risk-execution'];
for (const page of instancePermissionPages) {
  const content = read(`src/app/patch-manager/(pages)/${page}/page.tsx`);
  if (!content.includes('instPermissions=')) {
    throw new Error(`${page} 页面实例操作未传入后端 permission 字段`);
  }
}

const libraryPage = read('src/app/patch-manager/(pages)/library/page.tsx');
if (!libraryPage.includes('permissionPath="/patch-manager/settings/sources"')) {
  throw new Error('补丁库同步入库应检查补丁源 Edit 权限');
}
if (libraryPage.includes("record.permission?.includes('Operate')")) {
  throw new Error('全局共享补丁不应再检查实例数据权限');
}

for (const page of ['library/page.tsx', 'baseline/page.tsx', 'settings/_components/settings-content.tsx']) {
  const content = read(`src/app/patch-manager/(pages)/${page}`);
  if (content.includes('instPermissions=')) {
    throw new Error(`${page} 是全局共享资源，不应再检查实例数据权限`);
  }
}

const legacySettingsPage = read('src/app/patch-manager/(pages)/settings/page.tsx');
if (!legacySettingsPage.includes('<SettingsRedirect />')) {
  throw new Error('旧设置地址应按当前用户权限跳转到第一个可访问子菜单');
}

const sourceSettingsPage = read('src/app/patch-manager/(pages)/settings/sources/page.tsx');
if (!sourceSettingsPage.includes('<PatchSourcesSettings />')) {
  throw new Error('补丁源路由应渲染独立的补丁源模块');
}

const scanSettingsPage = read('src/app/patch-manager/(pages)/settings/scan/page.tsx');
if (!scanSettingsPage.includes('<ScanSettings />')) {
  throw new Error('扫描设置路由应渲染独立的扫描设置模块');
}

const targetPage = read('src/app/patch-manager/(pages)/target/page.tsx');
if (targetPage.includes('permissionPath="/patch-manager/baseline"')) {
  throw new Error('目标绑定基线不应检查全局共享基线的实例权限');
}
if (!targetPage.includes('permissionPath="/patch-manager/risk-execution"')) {
  throw new Error('目标立即评估应检查治理任务 Add 权限');
}

const baselinePage = read('src/app/patch-manager/(pages)/baseline/page.tsx');
if (!baselinePage.includes('permissionPath="/patch-manager/target"')) {
  throw new Error('基线绑定主机应检查目标管理 Edit 权限');
}
if (!baselinePage.includes('permissionPath="/patch-manager/risk-execution"')) {
  throw new Error('基线发起评估应检查治理任务 Add 权限');
}

const permissionWrapper = read('src/components/permission/index.tsx');
if (!permissionWrapper.includes('prevProps.instPermissions === nextProps.instPermissions')) {
  throw new Error('PermissionWrapper memo 比较必须包含实例权限，避免权限状态陈旧');
}

console.log('补丁管理菜单与按钮权限约束通过');
