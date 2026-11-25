import assert from 'node:assert/strict';
import test from 'node:test';
import { validateSingleOrGaugeData } from '@/app/ops-analysis/utils/compareQuery';

const nonNumericRows = [{ cpu: null }, { cpu: '高' }];

test('a configured calculation skips the field and gauge structure gates', () => {
  const count = { scalarCalc: { method: 'count' as const }, selectedFields: ['missing'] };
  assert.deepEqual(validateSingleOrGaugeData(nonNumericRows, 'single', count), { isValid: true });
  assert.deepEqual(
    validateSingleOrGaugeData(nonNumericRows, 'gauge', { scalarCalc: { method: 'count' } }),
    { isValid: true },
  );
  assert.deepEqual(
    validateSingleOrGaugeData(nonNumericRows, 'gauge', {
      scalarCalc: { method: 'avg' },
    }),
    { isValid: true },
  );
});

test('single and gauge without a calculation keep the existing gates', () => {
  assert.equal(
    validateSingleOrGaugeData(nonNumericRows, 'single', { selectedFields: ['cpu'] })?.isValid,
    true,
  );
  assert.equal(
    validateSingleOrGaugeData([{ host: 'a' }], 'single', { selectedFields: ['cpu'] })?.isValid,
    false,
  );
  assert.equal(
    validateSingleOrGaugeData(nonNumericRows, 'gauge', {})?.isValid,
    false,
  );
  assert.equal(
    validateSingleOrGaugeData([{ cpu: 10 }], 'gauge', {})?.isValid,
    true,
  );
});
