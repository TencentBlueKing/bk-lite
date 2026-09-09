import { describe, expect, it } from 'vitest';
import { toFiniteNumberIds } from '../incidentAlertIds';

describe('toFiniteNumberIds', () => {
  it('keeps numeric alert ids and drops bigint React keys', () => {
    expect(toFiniteNumberIds([12, '34', 56n, 'x'])).toEqual([12, 34]);
  });

  it('builds a Set of string|number without accepting Key[]', () => {
    const merged = Array.from(
      new Set<number>([1, 2, ...toFiniteNumberIds(['3', 4])])
    );
    expect(merged).toEqual([1, 2, 3, 4]);
  });
});
