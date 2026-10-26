import { describe, expect, it } from 'vitest';
import { seriesFoldOutline } from '../card-alert-fold';

describe('seriesFoldOutline', () => {
  it('默认实心，只有 outline 描边', () => {
    expect(seriesFoldOutline()).toBe(false);
    expect(seriesFoldOutline('solid')).toBe(false);
    expect(seriesFoldOutline('outline')).toBe(true);
    expect(seriesFoldOutline.length).toBe(1);
  });
});
