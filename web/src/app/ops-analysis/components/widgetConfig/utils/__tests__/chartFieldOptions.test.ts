import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTopNFieldSelectOptions } from '../chartFieldOptions';

test('value field options include string schema fields and preview keys', () => {
  const options = buildTopNFieldSelectOptions(
    [
      { key: 'source_ip', title: '上报IP', value_type: 'string' },
      { key: 'message', title: '日志内容', value_type: 'string' },
    ],
    [
      { value: '208036', name: '10.51.176.171' },
    ],
  );

  assert.deepEqual(
    options.map((option) => option.value),
    ['source_ip', 'message', 'value', 'name'],
  );
});
