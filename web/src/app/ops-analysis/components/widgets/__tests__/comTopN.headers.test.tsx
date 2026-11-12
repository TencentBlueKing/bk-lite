import { describe, expect, it } from 'vitest';
import { resolveTopNHeaderParts } from '../comTopN';

describe('ComTopN headers', () => {
  it('does not leave the name header blank on screen theme when the field has no schema title', () => {
    expect(
      resolveTopNHeaderParts('label', [{ key: 'count', title: '数量', value_type: 'number' }], {
        preferTitleOnly: true,
      }).full,
    ).toBe('label');
  });
});
