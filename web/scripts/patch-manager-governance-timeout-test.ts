import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const assertPresent = (content: string, pattern: RegExp, scope: string) => {
  if (!pattern.test(content)) throw new Error(`${scope} 缺少约束: ${pattern}`);
};
const assertAbsent = (content: string, pattern: RegExp, scope: string) => {
  if (pattern.test(content)) throw new Error(`${scope} 仍存在旧展示: ${pattern}`);
};

const page = read('src/app/patch-manager/(pages)/risk-execution/page.tsx');
const riskPendingPage = read('src/app/patch-manager/(pages)/risk-pending/page.tsx');
const baselinePage = read('src/app/patch-manager/(pages)/baseline/page.tsx');
const service = read('../server/apps/patch_mgmt/services/execution_record_service.py');

assertPresent(service, /"installing", "rebooting", "scanning", "reconciling"/, '结果确认中归为执行中');
assertPresent(service, /"failed", "reboot_failed", "pending_confirmation"/, '待人工确认归为失败');
assertPresent(page, /attempt\.started_at/, '步骤开始时间');
assertPresent(page, /attempt\.finished_at/, '步骤结束时间');
assertPresent(page, /attempt\.reason/, '超时与失败原因');
assertPresent(
  page,
  /\['failed',\s*'unknown',\s*'unmet'\]\.includes\(riskDetail\.status\)/,
  '仅可重试的终态展示重试',
);
assertPresent(page, /setInterval\(\(\) => \{[\s\S]{0,300}\},\s*2000\);/, '详情抽屉 2 秒轮询');
assertPresent(page, /const apiRef = useRef\(api\);[\s\S]{0,100}apiRef\.current = api;/, '详情请求使用稳定 API 引用');
assertPresent(page, /let polling = false;[\s\S]{0,300}if \(polling\) return;[\s\S]{0,300}polling = true;/, '详情轮询禁止并发请求');
assertPresent(page, /<Button type="link" size="small" onClick=\{\(\) => openDetail\(row\.id\)\}>详情<\/Button>/, '执行记录详情使用 Ant Design 链接按钮');
assertPresent(page, /requiredPermissions=\{\['Edit'\]\}[\s\S]{0,160}<Button type="link" size="small"[\s\S]{0,100}>取消<\/Button>/, '执行记录取消使用权限链接按钮');
assertPresent(page, /requiredPermissions=\{\['Edit'\]\}[\s\S]{0,160}<Button type="link" size="small" onClick=\{handleRetry\}>重试<\/Button>/, '执行详情重试使用权限链接按钮');
assertAbsent(page, /function LogBlock|<LogBlock\b|background:\s*'#1e1e1e'/, '执行详情原始黑色日志框');
assertPresent(riskPendingPage, /<Button type="link" size="small" onClick=\{\(\) => setDetailRecord/, '待治理风险详情使用 Ant Design 链接按钮');
assertPresent(riskPendingPage, /requiredPermissions=\{\['Add'\]\}[\s\S]{0,160}<Button type="link" size="small"[\s\S]{0,100}>治理<\/Button>/, '待治理风险治理使用权限链接按钮');
assertPresent(riskPendingPage, /requiredPermissions=\{\['Add'\]\}[\s\S]{0,160}<Button type="link" size="small"[\s\S]{0,100}>重启<\/Button>/, '待治理风险重启使用权限链接按钮');
assertAbsent(page, /<a\b/, '执行记录原生链接操作');
assertAbsent(riskPendingPage, /<a\b/, '待治理风险原生链接操作');
assertAbsent(baselinePage, /<a\b/, '基线管理原生链接操作');

console.log('补丁治理分层超时前端约束通过');
