import assert from 'node:assert/strict';

import { applyExecutionStreamEvent } from '../src/app/job/hooks/executionStreamState';

const gapLine =
  '[实时日志缺口] 省略 12 行；请以任务终态输出为准（终态可能截断）';
const withGap = applyExecutionStreamEvent(
  {},
  {
    target_key: 'ansible',
    stream: 'stdout',
    type: 'gap',
    line: gapLine,
    dropped_lines: 12,
  }
);

assert.equal(withGap.ansible.stdout, `${gapLine}\n`);
assert.equal(withGap.ansible.done, false);

const completed = applyExecutionStreamEvent(withGap, {
  target_key: 'ansible',
  type: 'done',
  status: 'success',
});

assert.equal(completed.ansible.stdout, `${gapLine}\n`);
assert.equal(completed.ansible.done, true);
assert.equal(completed.ansible.status, 'success');

console.log('job execution stream gap contract passed');
