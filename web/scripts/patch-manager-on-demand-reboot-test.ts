import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const assertPresent = (content: string, pattern: RegExp, scope: string) => {
  if (!pattern.test(content)) throw new Error(`${scope} 缺少约束: ${pattern}`);
};
const assertAbsent = (content: string, pattern: RegExp, scope: string) => {
  if (pattern.test(content)) throw new Error(`${scope} 仍包含旧逻辑: ${pattern}`);
};

const page = read('src/app/patch-manager/(pages)/risk-pending/page.tsx');
const globalStyles = read('src/styles/globals.css');

assertPresent(page, /i\.remediation\s*===\s*'pending_reboot'/, '待重启主机判定');
assertPresent(
  page,
  /hostIds\.size\s*>\s*0\s*&&\s*Array\.from\(hostIds\)\.every\(\(hostId\)\s*=>\s*pendingRebootHostIds\.has\(hostId\)\)/,
  '聚合行所有主机必须可重启',
);
assertPresent(page, /selectedRows\.length\s*>\s*0\s*&&\s*selectedRows\.every\(\(r\)\s*=>\s*canReboot\(r\.items\s*\|\|\s*\[\]\)\)/, '批量重启全选校验');
assertPresent(page, /patchManager\.risk\.rebootSelectionBlocked/, '批量重启禁用原因');
const dropdownZIndex = Number(globalStyles.match(/\.ant-dropdown\s*\{[^}]*z-index:\s*(\d+)/)?.[1]);
const rebootTooltipZIndex = Number(
  page.match(/<Tooltip[^>]*title=\{!batchCanReboot[\s\S]{0,180}zIndex=\{(\d+)\}/)?.[1],
);
if (!Number.isFinite(dropdownZIndex) || !Number.isFinite(rebootTooltipZIndex)) {
  throw new Error('无法读取 Dropdown 或一键重启 Tooltip 的层级');
}
if (rebootTooltipZIndex <= dropdownZIndex) {
  throw new Error(`一键重启 Tooltip 层级 ${rebootTooltipZIndex} 未高于 Dropdown 层级 ${dropdownZIndex}`);
}
assertPresent(page, /rebootable\s*&&\s*\([\s\S]{0,400}patchManager\.risk\.reboot/, '行内重启按钮按需显示');
assertAbsent(page, /patchManager\.risk\.noRebootableHosts[\s\S]{0,150}patchManager\.risk\.reboot/, '行内废弃的置灰重启按钮');
assertPresent(
  page,
  /api\.previewRebootRisk\(targetIds\)/,
  '重启弹窗从后端获取完整主机补丁范围',
);
assertPresent(page, /rebootScope\?\.items/, '重启确认表格使用冻结范围');
assertPresent(page, /scope_token:\s*rebootScope\?\.scope_token/, '重启提交携带范围指纹');
assertPresent(page, /code\s*===\s*'reboot_scope_changed'/, '范围变化后刷新并要求重新确认');
assertPresent(page, /patchManager\.risk\.autoRebootTitle/, '自动重启精确范围提示');
assertPresent(page, /patchManager\.risk\.autoRebootHelp/, '自动重启分支提示');
assertPresent(page, /patchManager\.risk\.onlyRequiredReboot/, '提交确认提示');
assertPresent(
  page,
  /patchManager\.risk\.autoReboot'\)\}[\s\S]{0,200}<Alert[\s\S]{0,200}type="warning"[\s\S]{0,200}showIcon[\s\S]{0,200}patchManager\.risk\.autoRebootTitle[\s\S]{0,600}<Switch[\s\S]{0,120}aria-label=\{t\('patchManager\.risk\.autoReboot'\)\}/,
  '自动重启标题、常驻 Alert 与开关按三行排列',
);
assertPresent(page, /<div style=\{\{ width: '100%', flex: 1, overflowY: 'auto' \}\}>/, '执行设置区域占满抽屉内容宽度');
assertPresent(page, /<Alert\s+style=\{\{ width: '100%', marginBottom: 12 \}\}/, '自动重启 Alert 占满内容宽度');
assertPresent(
  page,
  /const payload: Parameters<typeof api\.remediateRisk>\[0\][\s\S]{0,180}auto_reboot: autoReboot/,
  '治理请求复用 API 入参类型',
);
assertPresent(
  page,
  /checked=\{autoReboot\}[\s\S]{0,160}onChange=\{\(checked: boolean\) => setAutoReboot\(checked\)\}/,
  '自动重启开关传递明确的布尔值',
);
assertAbsent(page, /checkedChildren=|unCheckedChildren=/, '自动重启开关不应显示状态文字');
assertAbsent(page, /\{autoReboot\s*&&\s*\(\s*<Alert/, '自动重启提示不应随开关隐藏');

console.log('补丁治理按需重启前端约束通过');
