import { describe, expect, it, vi } from 'vitest';

import { createIdempotencyKey } from '../idempotencyKey';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('createIdempotencyKey', () => {
  it('uses randomUUID when the browser provides it', () => {
    const getRandomValues = vi.fn();
    expect(createIdempotencyKey({
      randomUUID: () => '11111111-1111-4111-8111-111111111111',
      getRandomValues,
    })).toBe('11111111-1111-4111-8111-111111111111');
    expect(getRandomValues).not.toHaveBeenCalled();
  });

  it('builds a uuid from getRandomValues when randomUUID is missing', () => {
    expect(createIdempotencyKey({
      getRandomValues: (values) => {
        values.fill(0);
        return values;
      },
    })).toBe('00000000-0000-4000-8000-000000000000');
  });

  it('still returns a uuid when web crypto is missing', () => {
    expect(createIdempotencyKey(undefined)).toMatch(UUID_V4);
  });
});
