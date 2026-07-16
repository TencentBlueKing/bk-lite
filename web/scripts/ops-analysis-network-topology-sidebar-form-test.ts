/**
 * 网络拓扑目录弹窗表单回归测试。
 *
 * 覆盖:
 * - 编辑网络拓扑时 label 宽度足够展示「WeOps Token」
 * - Token 密码框下方不再展示旧的保留提示
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const sidebarSource = readFileSync(
  resolve(process.cwd(), 'src/app/ops-analysis/components/sidebar.tsx'),
  'utf8',
);

assert.match(
  sidebarSource,
  /labelCol=\{\{\s*flex:\s*'1(?:0[4-9]|[1-9]\d{2,})px'\s*\}\}/,
  '网络拓扑弹窗表单应使用至少 104px 的固定 label 宽度,避免 WeOps Token 被截断',
);

assert.doesNotMatch(
  sidebarSource,
  /extra=\{\s*modalAction === 'edit'[\s\S]*?tokenEditHint[\s\S]*?\}/,
  '编辑网络拓扑时不应在 Token 输入框下方展示 tokenEditHint',
);

console.log('ops-analysis network topology sidebar form tests passed');
