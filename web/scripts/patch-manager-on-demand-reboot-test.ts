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
assertPresent(page, /所选范围包含非待重启主机/, '批量重启禁用原因');
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
assertPresent(page, /rebootable\s*&&\s*\([\s\S]{0,300}>重启<\//, '行内重启按钮按需显示');
assertAbsent(page, /该条目无主机[\s\S]{0,150}>重启<\//, '行内废弃的置灰重启按钮');
assertPresent(
  page,
  /filter\(\(i:\s*RiskItem\)\s*=>\s*i\.remediation\s*===\s*'pending_reboot'\)[\s\S]{0,120}i\.host_id/,
  '重启请求仅携带待重启主机',
);
assertPresent(page, /仅自动重启明确需要重启的主机/, '自动重启精确范围提示');
assertPresent(page, /无需重启的主机将跳过重启/, '无需重启分支提示');
assertPresent(page, /无法确认的主机将进入待重启并等待人工处理/, '未知分支提示');
assertPresent(page, /仅自动重启检测为需要重启的主机/, '提交确认提示');

console.log('补丁治理按需重启前端约束通过');
