import { describe, expect, it } from 'vitest';
import { collectSelectedAlertIds } from '../incidentAlertRelations';

describe('collectSelectedAlertIds', () => {
  it('keeps numeric alert ids and drops bigint React keys', () => {
    expect(collectSelectedAlertIds([12, '34', 56n, 'x'])).toEqual([12, 34]);
  });

  it('builds a Set of numbers without accepting Key[]', () => {
    const merged = Array.from(
      new Set<number>([1, 2, ...collectSelectedAlertIds(['3', 4])])
    );
    expect(merged).toEqual([1, 2, 3, 4]);
  });
});
