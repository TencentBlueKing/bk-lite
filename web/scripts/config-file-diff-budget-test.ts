import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const diffUtilsPath = path.join(
  root,
  'src/app/cmdb/(pages)/assetData/detail/configFiles/components/diffUtils.ts'
);
const compareDrawerPath = path.join(
  root,
  'src/app/cmdb/(pages)/assetData/detail/configFiles/components/compareDrawer.tsx'
);
const zhLocalePath = path.join(root, 'src/app/cmdb/locales/zh.json');
const enLocalePath = path.join(root, 'src/app/cmdb/locales/en.json');

interface SlimRow {
  leftText: string;
  rightText: string;
  status: string;
  leftNumber: number | null;
  rightNumber: number | null;
}

const slim = (rows: Array<{
  leftText: string;
  rightText: string;
  status: string;
  leftNumber: number | null;
  rightNumber: number | null;
}>): SlimRow[] => rows.map((row) => ({
  leftText: row.leftText,
  rightText: row.rightText,
  status: row.status,
  leftNumber: row.leftNumber,
  rightNumber: row.rightNumber,
}));

const makeLines = (count: number, prefix: string): string => (
  Array.from({ length: count }, (_, index) => `${prefix}-${index}`).join('\n')
);

const expectAligned = (
  result: { kind?: string; rows?: SlimRow[] },
  expected: SlimRow[],
  message: string
) => {
  assert.equal(result.kind, 'aligned', message);
  assert.ok(Array.isArray(result.rows), message);
  assert.deepEqual(slim(result.rows as SlimRow[]), expected, message);
};

async function main() {
  const {
    buildSideBySideDiffRows,
    buildInlineSegments,
    MAX_DIFF_LCS_CELLS,
  } = await import(pathToFileURL(diffUtilsPath).href);

  assert.equal(
    MAX_DIFF_LCS_CELLS,
    1_000_000,
    'LCS 必须使用命名常量 MAX_DIFF_LCS_CELLS=1000000，按 (n+1)*(m+1) 计'
  );

  expectAligned(
    buildSideBySideDiffRows('', ''),
    [{ leftText: '', rightText: '', status: 'same', leftNumber: 1, rightNumber: 1 }],
    '空文件应对齐为一行 same'
  );
  expectAligned(
    buildSideBySideDiffRows('', 'a'),
    [{ leftText: '', rightText: 'a', status: 'changed', leftNumber: 1, rightNumber: 1 }],
    '空左文件应对齐为 changed'
  );
  expectAligned(
    buildSideBySideDiffRows('a', ''),
    [{ leftText: 'a', rightText: '', status: 'changed', leftNumber: 1, rightNumber: 1 }],
    '空右文件应对齐为 changed'
  );
  expectAligned(
    buildSideBySideDiffRows('a\r\nb\r\nc', 'a\nb\nc'),
    [
      { leftText: 'a', rightText: 'a', status: 'same', leftNumber: 1, rightNumber: 1 },
      { leftText: 'b', rightText: 'b', status: 'same', leftNumber: 2, rightNumber: 2 },
      { leftText: 'c', rightText: 'c', status: 'same', leftNumber: 3, rightNumber: 3 },
    ],
    'CRLF 应与 LF 按行对齐'
  );
  expectAligned(
    buildSideBySideDiffRows('a\nc', 'a\nb\nc'),
    [
      { leftText: 'a', rightText: 'a', status: 'same', leftNumber: 1, rightNumber: 1 },
      { leftText: '', rightText: 'b', status: 'added', leftNumber: null, rightNumber: 2 },
      { leftText: 'c', rightText: 'c', status: 'same', leftNumber: 2, rightNumber: 3 },
    ],
    '新增行应对齐为 added'
  );
  expectAligned(
    buildSideBySideDiffRows('a\nb\nc', 'a\nc'),
    [
      { leftText: 'a', rightText: 'a', status: 'same', leftNumber: 1, rightNumber: 1 },
      { leftText: 'b', rightText: '', status: 'removed', leftNumber: 2, rightNumber: null },
      { leftText: 'c', rightText: 'c', status: 'same', leftNumber: 3, rightNumber: 2 },
    ],
    '删除行应对齐为 removed'
  );
  expectAligned(
    buildSideBySideDiffRows('a\nx\nc', 'a\ny\nc'),
    [
      { leftText: 'a', rightText: 'a', status: 'same', leftNumber: 1, rightNumber: 1 },
      { leftText: 'x', rightText: 'y', status: 'changed', leftNumber: 2, rightNumber: 2 },
      { leftText: 'c', rightText: 'c', status: 'same', leftNumber: 3, rightNumber: 3 },
    ],
    '修改行应对齐为 changed'
  );
  expectAligned(
    buildSideBySideDiffRows('a\na\nb', 'a\nb'),
    [
      { leftText: 'a', rightText: 'a', status: 'same', leftNumber: 1, rightNumber: 1 },
      { leftText: 'a', rightText: '', status: 'removed', leftNumber: 2, rightNumber: null },
      { leftText: 'b', rightText: 'b', status: 'same', leftNumber: 3, rightNumber: 2 },
    ],
    '重复行应保持现有 LCS 对齐'
  );

  assert.deepEqual(
    buildInlineSegments('hello world', 'hello there'),
    {
      left: [{ text: 'hello ', changed: false }, { text: 'world', changed: true }],
      right: [{ text: 'hello ', changed: false }, { text: 'there', changed: true }],
    },
    '行内高亮应保留公共前后缀'
  );
  assert.deepEqual(
    buildInlineSegments('same', 'same'),
    {
      left: [{ text: 'same', changed: false }],
      right: [{ text: 'same', changed: false }],
    },
    '相同文本不应标记行内变更'
  );

  const atBudgetLeft = makeLines(999, 'L');
  const atBudgetRight = makeLines(999, 'R');
  const atBudget = buildSideBySideDiffRows(atBudgetLeft, atBudgetRight);
  assert.equal(
    atBudget.kind,
    'aligned',
    '阈值内 (999+1)*(999+1)=1000000 仍应走 LCS'
  );
  assert.ok(Array.isArray(atBudget.rows) && atBudget.rows.length > 0, '阈值内必须返回对齐行');

  const unequalAtBudget = buildSideBySideDiffRows(makeLines(499, 'L'), makeLines(1999, 'R'));
  assert.equal(
    unequalAtBudget.kind,
    'aligned',
    '阈值内不等长 (499+1)*(1999+1)=1000000 仍应走 LCS'
  );

  const overBudget = buildSideBySideDiffRows(makeLines(1000, 'L'), makeLines(1000, 'R'));
  assert.equal(overBudget.kind, 'over_budget', '超过 MAX_DIFF_LCS_CELLS 必须返回 over_budget');
  assert.ok(
    typeof overBudget.cellCount === 'number' && overBudget.cellCount > MAX_DIFF_LCS_CELLS,
    'over_budget 必须给出按 (n+1)*(m+1) 计的 cellCount'
  );
  assert.equal('rows' in overBudget, false, '超预算禁止静默返回错误对齐 rows');

  const hugeStart = Date.now();
  const huge = buildSideBySideDiffRows(makeLines(20000, 'L'), makeLines(20000, 'R'));
  const hugeElapsed = Date.now() - hugeStart;
  assert.equal(huge.kind, 'over_budget', '20000x20000 必须返回 over_budget，不得走完整 DP');
  assert.ok(
    hugeElapsed < 1000,
    `20000x20000 必须在 1s 内返回 over_budget，实际 ${hugeElapsed}ms`
  );
  assert.equal(
    huge.cellCount,
    20001 * 20001,
    '20000x20000 的 cellCount 必须按 (n+1)*(m+1) 计'
  );

  const diffUtilsSource = readFileSync(diffUtilsPath, 'utf8');
  const compareDrawerSource = readFileSync(compareDrawerPath, 'utf8');
  const zhLocale = JSON.parse(readFileSync(zhLocalePath, 'utf8')) as {
    ConfigFile: Record<string, string>;
  };
  const enLocale = JSON.parse(readFileSync(enLocalePath, 'utf8')) as {
    ConfigFile: Record<string, string>;
  };

  assert.match(
    diffUtilsSource,
    /export const MAX_DIFF_LCS_CELLS = 1_000_000/,
    '必须导出命名常量 MAX_DIFF_LCS_CELLS=1000000'
  );
  const budgetGuardIndex = diffUtilsSource.search(
    /if\s*\(\s*cellCount\s*>\s*MAX_DIFF_LCS_CELLS\s*\)/
  );
  const matrixIndex = diffUtilsSource.search(
    /Array\.from\(\{\s*length:\s*leftLength\s*\+\s*1/
  );
  assert.ok(budgetGuardIndex >= 0, '超预算必须在分配矩阵前用 cellCount > MAX_DIFF_LCS_CELLS 拦截');
  assert.ok(matrixIndex > budgetGuardIndex, 'LCS 矩阵只能在预算守卫之后分配');
  assert.doesNotMatch(
    diffUtilsSource,
    /new Worker|worker_threads/,
    '禁止把完整矩阵搬进 Worker 后继续无上限分配'
  );
  assert.match(
    diffUtilsSource,
    /菜单「资产」→「配置文件」/,
    '源码注释必须记录真实菜单文案：资产 → 配置文件'
  );
  assert.match(
    diffUtilsSource,
    /页头「配置文件列表」/,
    '源码注释必须记录真实页头：配置文件列表'
  );
  assert.match(
    diffUtilsSource,
    /按钮「与上版本对比」/,
    '源码注释必须记录真实按钮：与上版本对比'
  );
  assert.doesNotMatch(diffUtilsSource, /与上一版本对比/);
  assert.match(
    diffUtilsSource,
    /抽屉「版本对比」/,
    '源码注释必须记录真实抽屉标题：版本对比'
  );

  assert.match(compareDrawerSource, /kind === 'over_budget'|kind !== 'aligned'/);
  assert.match(compareDrawerSource, /ConfigFile\.diffOverBudgetHint/);
  assert.match(
    compareDrawerSource,
    /leftContent\.split\(|plainLeftLines|overBudgetLeft/,
    '超预算必须左右纯文本对照，而不是错误 LCS 对齐'
  );
  assert.doesNotMatch(compareDrawerSource, /new Worker|worker_threads/);

  assert.equal(zhLocale.ConfigFile.compareWithPrev, '与上版本对比');
  assert.equal(zhLocale.ConfigFile.title, '配置文件列表');
  assert.equal(zhLocale.ConfigFile.versionCompare, '版本对比');
  assert.equal(
    typeof zhLocale.ConfigFile.diffOverBudgetHint,
    'string',
    '抽屉超预算必须有明确中文提示'
  );
  assert.match(
    zhLocale.ConfigFile.diffOverBudgetHint,
    /无法.*对齐|原文对照/,
    '中文提示必须说明无法对齐并改为原文对照'
  );
  assert.doesNotMatch(zhLocale.ConfigFile.diffOverBudgetHint, /与上一版本对比/);
  assert.equal(
    typeof enLocale.ConfigFile.diffOverBudgetHint,
    'string',
    '抽屉超预算必须有明确英文提示'
  );

  console.log('config-file-diff-budget-test OK');
}

void main();
