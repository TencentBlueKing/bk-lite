import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const settingsPage = read('src/app/patch-manager/(pages)/settings/page.tsx');
const targetPage = read('src/app/patch-manager/(pages)/target/page.tsx');
const types = read('src/app/patch-manager/types/index.ts');
const sourceLocales = `${read('src/app/patch-manager/locales/zh.json')}\n${read('src/app/patch-manager/locales/en.json')}`;
const baseZhLocales = JSON.parse(read('src/locales/zh.json'));
const baseEnLocales = JSON.parse(read('src/locales/en.json'));
const sourceOriginBadge = read('src/components/source-origin-badge/index.tsx');

for (const required of [
  "import Password from '@/components/password'",
  "const SAVED_SECRET = '********'",
  'record.has_auth_password ? SAVED_SECRET : undefined',
  'payload.auth_password === SAVED_SECRET',
  'editingSource?.has_auth_password && !payload.auth_password',
  "label: 'patchManager.catalogUrl'",
  "label: 'patchManager.repoUrl'",
  'tooltip={sourceUrlHelp}',
  'patchManager.settingsPage.wsusUrlHelp',
  'patchManager.settingsPage.yumRepoUrlHelp',
  'patchManager.settingsPage.dnfRepoUrlHelp',
  'patchManager.settingsPage.aptRepoUrlHelp',
  "sourceType !== 'wsus'",
  "patchManager.settingsPage.authUserRequired",
  "patchManager.settingsPage.authPasswordRequired",
  'has_auth_password?: boolean',
  'is_builtin: boolean',
  "import SourceOriginBadge from '@/components/source-origin-badge'",
  'const { isSuperUser } = useUserInfoContext()',
  '<SourceOriginBadge kind="builtin"',
  "title: t('patchManager.builtin')",
  "dataIndex: 'is_builtin'",
  "t('patchManager.yes')",
  "t('patchManager.no')",
  'r.is_builtin ? (',
  '<Button type="link" danger disabled',
  'patchManager.settingsPage.builtinDeleteDisabled',
]) {
  if (!`${settingsPage}\n${types}\n${read('src/app/patch-manager/api/index.ts')}`.includes(required)) {
    throw new Error(`补丁源编辑表单缺少约束: ${required}`);
  }
}

for (const message of [
  '"builtinDeleteDisabled": "内置补丁源暂不支持删除"',
  '"builtinDeleteDisabled": "Built-in patch sources cannot be deleted yet"',
]) {
  if (!sourceLocales.includes(message)) {
    throw new Error(`内置源禁用删除提示缺少双语文案: ${message}`);
  }
}

for (const removed of ['extra={sourceUrlHelp}', 'restorePatchSourceDefaults', 'restoreDefaults', 'confirmRestoreSource', 'sourceRestored']) {
  if (`${settingsPage}\n${read('src/app/patch-manager/api/index.ts')}\n${sourceLocales}`.includes(removed)) {
    throw new Error(`补丁源页面不应保留交互: ${removed}`);
  }
}

const sourceNameColumn = settingsPage.match(
  /title: t\('patchManager\.pluginName'\),([\s\S]*?)title: t\('patchManager\.builtin'\)/,
)?.[1] || '';
if (sourceNameColumn.includes('SourceOriginBadge')) {
  throw new Error('内置属性必须独立成列，不能放在补丁源名称列');
}

const sourceForm = settingsPage.match(/<Form form=\{form\}([\s\S]*?)<\/Form>/)?.[0] || '';
if (!sourceForm || /name=["']is_builtin["']/.test(sourceForm)) {
  throw new Error('内置属性不能出现在补丁源新增或编辑表单');
}

for (const [locale, messages, expected] of [
  ['zh', baseZhLocales, { custom: '自定义', imported: '已导入' }],
  ['en', baseEnLocales, { custom: 'Custom', imported: 'Imported' }],
] as const) {
  for (const [key, value] of Object.entries(expected)) {
    if (messages.common?.[key] !== value) {
      throw new Error(`来源徽标缺少 ${locale} 文案 common.${key}`);
    }
  }
}
if (!sourceOriginBadge.includes('t(LABEL_KEY_BY_KIND[kind])')) {
  throw new Error('来源徽标必须只解析当前类型的翻译键');
}

for (const example of [
  'https://mirrors.aliyun.com/rockylinux/8/BaseOS/x86_64/os/',
  'https://mirrors.aliyun.com/rockylinux/9/BaseOS/x86_64/os/',
  'https://mirrors.aliyun.com/ubuntu',
]) {
  if (!sourceLocales.includes(example)) {
    throw new Error(`补丁源表单缺少真实仓库示例: ${example}`);
  }
}

if (!settingsPage.includes('<Password') || settingsPage.includes('<Input.Password')) {
  throw new Error('补丁源认证密码必须使用项目 Password 组件');
}

const sourceFooter = settingsPage.match(/footer=\{([\s\S]*?)\}\s*>\s*<Form form=\{form\}/)?.[1] || '';
for (const key of ['patchManager.cancel', 'patchManager.testConnection', 'patchManager.save']) {
  if (!sourceFooter.includes(key)) throw new Error(`补丁源弹窗 footer 缺少双语按钮 ${key}`);
}
if (!(sourceFooter.indexOf('patchManager.cancel') < sourceFooter.indexOf('patchManager.testConnection')
  && sourceFooter.indexOf('patchManager.testConnection') < sourceFooter.indexOf('patchManager.save'))) {
  throw new Error('补丁源弹窗按钮顺序必须是：取消、测试连通性、保存');
}

const sourceConnectivityAlert = settingsPage.match(
  /\{connectivityResult && \(\s*<Alert([\s\S]*?)\/>\s*\)\}/,
)?.[1] || '';
if (!sourceConnectivityAlert.includes('closable')) {
  throw new Error('补丁源连通性测试结果必须支持手动关闭');
}
if (!sourceConnectivityAlert.includes('key={connectivityResult.checkedAt}')) {
  throw new Error('补丁源连通性测试结果关闭后，再次测试时必须重新显示');
}

const targetFooter = targetPage.match(/footer=\{([\s\S]*?)\}\s*>\s*<Form layout="vertical" form=\{form\}/)?.[1] || '';
if (!(targetFooter.indexOf('patchManager.cancel') < targetFooter.indexOf('patchManager.testConnection')
  && targetFooter.indexOf('patchManager.testConnection') < targetFooter.indexOf("editingTarget ? t('patchManager.save') : t('patchManager.targetPage.create')"))) {
  throw new Error('目标录入抽屉按钮顺序必须是：取消、测试连通性、保存/创建');
}

const targetConnectivityAlert = targetPage.match(
  /\{connectivityResult && \(\s*<Alert([\s\S]*?)\/>\s*\)\}/,
)?.[1] || '';
if (!targetConnectivityAlert.includes('closable')) {
  throw new Error('目标连通性测试结果必须支持手动关闭');
}
if (!targetConnectivityAlert.includes('key={connectivityResult.checkedAt}')) {
  throw new Error('目标连通性测试结果关闭后，再次测试时必须重新显示');
}

console.log('补丁源与目标录入表单约束通过');
