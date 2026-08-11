import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveSingleDescriptionText } from '../singleDescription';

test('resolveSingleDescriptionText returns raw string for selected field', () => {
  assert.equal(
    resolveSingleDescriptionText({ note: '  46 / 48  ' }, 'note'),
    '  46 / 48  ',
  );
});

test('resolveSingleDescriptionText returns undefined when field missing or empty', () => {
  assert.equal(resolveSingleDescriptionText({ note: '' }, 'note'), undefined);
  assert.equal(resolveSingleDescriptionText({ note: null }, 'note'), undefined);
  assert.equal(resolveSingleDescriptionText({ note: 'x' }, undefined), undefined);
  assert.equal(resolveSingleDescriptionText({ note: 'x' }, '  '), undefined);
  assert.equal(resolveSingleDescriptionText({ note: 'x' }, 'other'), undefined);
});

test('resolveSingleDescriptionText preserves zero and false as raw strings', () => {
  assert.equal(resolveSingleDescriptionText({ note: 0 }, 'note'), '0');
  assert.equal(resolveSingleDescriptionText({ note: false }, 'note'), 'false');
});
