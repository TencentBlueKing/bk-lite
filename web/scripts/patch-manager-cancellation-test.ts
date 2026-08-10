import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const assertPresent = (content: string, pattern: RegExp, scope: string) => {
  if (!pattern.test(content)) throw new Error(`${scope} 缺少约束: ${pattern}`);
};
const assertAbsent = (content: string, pattern: RegExp, scope: string) => {
  if (pattern.test(content)) throw new Error(`${scope} 仍包含废弃交互: ${pattern}`);
};

const api = read('src/app/patch-manager/api/index.ts');
const page = read('src/app/patch-manager/(pages)/risk-execution/page.tsx');
const riskPendingPage = read('src/app/patch-manager/(pages)/risk-pending/page.tsx');
const targetPage = read('src/app/patch-manager/(pages)/target/page.tsx');

assertPresent(
  api,
  /cancelGovernanceTask\s*=\s*async\s*\(id:\s*number,\s*reason:\s*string\)/,
  '取消 API 原因参数',
);
assertPresent(api, /governance\/\$\{id\}\/cancel\/`,\s*\{\s*reason\s*\}/, '取消 API 请求体');
assertPresent(page, /partial_cancelled:\s*'warning'/, '部分取消状态颜色');
assertPresent(page, /api\.cancelGovernanceTask\([^,]+,\s*cancelReason\.trim\(\)\)/, '取消提交');
assertPresent(page, /patchManager\.execution\.cancelReason/, '取消原因双语输入');
assertPresent(page, /cancelled_by/, '取消人展示');
assertPresent(page, /cancelled_at/, '取消时间展示');
assertPresent(page, /cancel_reason/, '取消原因展示');
assertPresent(
  page,
  /patchManager\.execution\.cancelInfo[\s\S]{0,800}patchManager\.execution\.cancelledBy[\s\S]{0,300}patchManager\.execution\.cancelledAt[\s\S]{0,300}patchManager\.execution\.cancelReason/,
  '取消信息归入当前风险项执行详情',
);
assertPresent(page, /okText=\{t\('patchManager\.confirm'\)\}/, '取消弹窗确认按钮文案');
assertPresent(page, /cancelText=\{t\('patchManager\.cancel'\)\}/, '取消弹窗返回按钮文案');
assertPresent(page, /patchManager\.execution\.cancelWaitingOnly/, '取消弹窗安全提示');
assertPresent(page, /patchManager\.execution\.cancelHelp/, '取消弹窗安全说明');
assertAbsent(page, /<Input\.TextArea[\s\S]{0,500}\bshowCount\b/, '取消原因字数统计');
assertPresent(page, /canCancel:\s*Boolean\(task\.can_cancel\)/, '取消资格由后端主机状态决定');
assertPresent(page, /row\.canCancel[\s\S]{0,700}patchManager\.cancel/, '可取消任务按钮');

assertPresent(page, /setInterval\(\(\) => \{[\s\S]{0,300}\},\s*PATCH_MANAGER_POLL_INTERVAL_MS\);/, '执行记录统一 5 秒轮询');
assertPresent(riskPendingPage, /setInterval\(\(\) => \{[\s\S]{0,300}\},\s*PATCH_MANAGER_POLL_INTERVAL_MS\);/, '待治理风险统一 5 秒轮询');
assertPresent(targetPage, /setInterval\(\(\) => \{[\s\S]{0,300}\},\s*pollIntervalMs\);/, '目标管理由刷新选择器控制轮询');

console.log('补丁治理取消前端约束通过');
