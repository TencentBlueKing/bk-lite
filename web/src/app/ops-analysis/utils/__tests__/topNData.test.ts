import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildTopNItems,
  coerceTopNNumericValue,
  resolveTopNBarPercent,
  resolveTopNMaxValue,
} from '../topNData';

test('numeric strings coerce, IPs and blanks stay empty', () => {
  assert.equal(coerceTopNNumericValue('208036'), 208036);
  assert.equal(coerceTopNNumericValue(208036), 208036);
  assert.equal(coerceTopNNumericValue('0'), 0);
  assert.equal(coerceTopNNumericValue('10.51.176.171'), null);
  assert.equal(coerceTopNNumericValue(''), null);
  assert.equal(coerceTopNNumericValue(true), null);
});

test('log top rows keep names and convert string hits', () => {
  const items = buildTopNItems(
    [
      { value: '208036', name: '10.51.176.171' },
      { value: 'not-a-number', name: '10.51.176.50' },
    ],
    'name',
    'value',
  );

  assert.deepEqual(items, [
    { name: '10.51.176.171', value: 208036 },
    { name: '10.51.176.50', value: null },
  ]);
  assert.equal(resolveTopNMaxValue(items), 208036);
  assert.equal(resolveTopNBarPercent(items[1].value, 208036), 0);
});
