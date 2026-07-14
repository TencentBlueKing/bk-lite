import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

import { formatDurationMs } from '../src/app/opspilot/utils/duration';

const cases: Array<[number | null | undefined, string]> = [
  [undefined, '0ms'],
  [null, '0ms'],
  [0, '0ms'],
  [999, '999ms'],
  [1000, '1秒'],
  [1500, '1.5秒'],
  [38369, '38.4秒'],
  [59999, '59.9秒'],
  [60000, '1分钟'],
  [61000, '1分钟1秒'],
  [3661000, '1小时1分钟1秒'],
];

for (const [input, expected] of cases) {
  assert.equal(formatDurationMs(input), expected, `${input} should format as ${expected}`);
}

const root = process.cwd();
const logInfoPage = fs.readFileSync(path.join(root, 'src/app/opspilot/(pages)/studio/detail/logInfo/page.tsx'), 'utf8');
const executionPreviewPanel = fs.readFileSync(path.join(root, 'src/app/opspilot/components/chatflow/ExecutionPreviewPanel.tsx'), 'utf8');

assert.match(logInfoPage, /formatDurationMs\(duration\)/, 'workflow log table should use formatDurationMs');
assert.match(executionPreviewPanel, /formatDurationMs\(item\.duration_ms\)/, 'workflow execution preview should use formatDurationMs');
assert.doesNotMatch(logInfoPage, /\$\{duration \|\| 0\}ms/, 'workflow log table should not hard-code ms');
assert.doesNotMatch(executionPreviewPanel, /\$\{duration\}ms/, 'workflow execution preview should not hard-code ms');

console.log('workflow duration format validation passed');
