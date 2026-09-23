import assert from 'node:assert/strict';
import test from 'node:test';
import { toComparableNumber } from '../compareQuery';
import { validateMultiValueData } from '../multiValueData';

test('unmapped multi value still reads label or name plus value text', () => {
  const parsed = validateMultiValueData(
    [
      { name: '主机', value: 'ok' },
      { label: '状态', value: '1abc' },
    ],
    '数据格式不匹配',
  );

  assert.equal(parsed.isValid, true);
  assert.deepEqual(parsed.items, [
    { label: '主机', value: 'ok' },
    { label: '状态', value: '1abc' },
  ]);
});

test('mapped multi value reads selected columns and keeps text', () => {
  const parsed = validateMultiValueData(
    [{ host: 'web-1', status: 'degraded' }],
    '数据格式不匹配',
    { labelField: 'host', valueField: 'status' },
  );

  assert.equal(parsed.isValid, true);
  assert.deepEqual(parsed.items, [{ label: 'web-1', value: 'degraded' }]);
});

test('single and gauge treat incomplete numbers as empty', () => {
  assert.equal(toComparableNumber('12'), 12);
  assert.equal(toComparableNumber('1abc'), null);
  assert.equal(toComparableNumber(''), null);
});
