import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(
  resolve(here, '../src/app/cmdb/(pages)/assetData/detail/baseInfo/list.tsx'),
  'utf8'
);

assert.doesNotMatch(
  source,
  /item\.is_required &&/,
  '详情页不得用 is_required && 渲染必填标记：数字 0 会被 React 画进标签（如「U数0」）'
);
assert.match(
  source,
  /item\.is_required \? \(/,
  '详情页必填标记必须用三元，避免 0 被当成文本'
);

const andResult = 0 && 'mark';
const ternaryResult = 0 ? 'mark' : null;
assert.equal(andResult, 0, 'React 的 && 会把数字 0 渲染成文本');
assert.equal(ternaryResult, null, '三元在 is_required=0 时不应渲染任何节点');

console.log('PASS cmdb-detail-required-mark');
