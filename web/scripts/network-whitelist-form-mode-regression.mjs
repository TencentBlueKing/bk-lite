import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const pagePath = path.join(process.cwd(), 'src/app/system-manager/(pages)/settings/network-whitelist/page.tsx');
const modalPath = path.join(process.cwd(), 'src/app/system-manager/components/network-whitelist-form-modal/index.tsx');
const modalStylePath = path.join(
  process.cwd(),
  'src/app/system-manager/components/network-whitelist-form-modal/networkWhitelistFormModal.module.scss',
);
const zhLocalePath = path.join(process.cwd(), 'src/app/system-manager/locales/zh.json');
const enLocalePath = path.join(process.cwd(), 'src/app/system-manager/locales/en.json');
const source = fs.readFileSync(pagePath, 'utf8');

assert.ok(fs.existsSync(modalPath), '白名单表单应提取为可在 Storybook 独立预览的 app-local 组件');
const modalSource = fs.readFileSync(modalPath, 'utf8');
const modalStyleSource = fs.readFileSync(modalStylePath, 'utf8');
const zhContent = JSON.parse(fs.readFileSync(zhLocalePath, 'utf8')).system.settings.networkWhitelist.content;
const enContent = JSON.parse(fs.readFileSync(enLocalePath, 'utf8')).system.settings.networkWhitelist.content;

assert.match(
  modalSource,
  /!editing\s*&&\s*\([\s\S]*?<Segmented[\s\S]*?onChange=/,
  '创建时应显示清晰的域名/网段分段选择，编辑时不应渲染类型控件',
);
const typeSelectorProps =
  modalSource.match(/<Segmented<NetworkWhitelistEntryType>([\s\S]*?)className=/)?.[1] ?? '';
assert.match(typeSelectorProps, /size="small"/, '网段和域名切换应使用小尺寸控件');
assert.doesNotMatch(typeSelectorProps, /\bblock\b/, '网段和域名切换不应占满整行');
assert.ok(
  modalSource.indexOf('networkWhitelist.entryTypeHint') > modalSource.indexOf('<Segmented<NetworkWhitelistEntryType>'),
  '保存后不可变更的说明应放在类型切换控件下方',
);
assert.doesNotMatch(
  modalSource,
  /disabled=\{!!editing\}/,
  '编辑时不应通过禁用控件表示类型锁定，而应完全隐藏类型控件',
);
assert.doesNotMatch(modalSource, /name="remark"[\s\S]{0,300}rules=/, '备注在新增和编辑时都必须是可选字段');
assert.doesNotMatch(modalSource, /networkWhitelist\.enabledHint/, '启用项只展示标题和开关，不应附加解释文案');
assert.doesNotMatch(modalSource, /SafetyCertificateOutlined|styles\.titleIcon/, '弹窗标题不应展示装饰图标');
assert.match(
  modalSource,
  /<Form\.Item[\s\S]{0,200}name="enabled"[\s\S]{0,200}label=\{t\('system\.settings\.networkWhitelist\.enabled'\)\}/,
  '启用项应使用与网段和备注一致的上下两行表单布局',
);
assert.doesNotMatch(modalSource, /styles\.policyRow/, '启用项不应使用带边框的独立容器');
for (const selector of ['typeSection', 'policyRow']) {
  const block = modalStyleSource.match(new RegExp(`\\.${selector}\\s*\\{([\\s\\S]*?)\\}`))?.[1] ?? '';
  assert.doesNotMatch(block, /background\s*:/, `${selector} 外层容器不应使用灰色背景`);
  assert.doesNotMatch(block, /border\s*:/, `${selector} 外层容器不应使用边框`);
}
const typeSelectorStyle = modalStyleSource.match(/\.typeSelector\s*\{([\s\S]*?)\n\}/)?.[1] ?? '';
assert.match(typeSelectorStyle, /width:\s*fit-content/, '类型切换应按内容收缩，不应保留过长轨道');
assert.doesNotMatch(typeSelectorStyle, /background:\s*var\(--color-fill-2\)/, '类型切换不应使用整条灰色背景');
assert.match(
  typeSelectorStyle,
  /ant-segmented-item-selected[\s\S]*?background:\s*var\(--color-primary-bg-active\)/,
  '类型切换选中项应使用清晰的主色浅底',
);
assert.match(source, /<NetworkWhitelistFormModal/, '页面应复用 Storybook 验证过的白名单表单组件');
assert.match(source, /<CustomTable<NetworkWhiteListItem>[\s\S]*?dataSource=\{dataSource\}/, '页面应使用表格展示白名单');
assert.doesNotMatch(source, /dataSource=\{builtInEntries\}/, '内置条目不应在白名单管理页面展示');
assert.match(zhContent, /匹配.*跳过.*拦截/, '说明应使用普通用户能理解的语言解释白名单用于跳过拦截');
assert.doesNotMatch(zhContent, /系统管理|OpsPilot|LLM|云元数据/, '页面简介不应罗列具体 App 或强调云元数据限制');
assert.match(enContent, /Matching.*bypass.*blocking/i, '英文说明应同步表达匹配目标会跳过拦截');
assert.doesNotMatch(enContent, /System Management|OpsPilot|LLM|cloud metadata/i, '英文简介不应罗列具体 App 或云元数据限制');

console.log('PASS network-whitelist-form-mode');
