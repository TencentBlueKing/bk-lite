import { describe, expect, it } from 'vitest';
import { resolveTableDimensions } from './tableHeight';

describe('resolveTableDimensions', () => {
  it('does not lock a viewport-tall body when scroll.y is auto', () => {
    expect(resolveTableDimensions({
      scrollY: 'auto',
      viewportHeight: 900,
      parentHeight: 720,
      size: 'middle',
      hasPagination: true,
    })).toEqual({
      tableHeight: undefined,
      containerHeight: undefined,
    });
  });

  it('still honors an explicit pixel body height', () => {
    expect(resolveTableDimensions({
      scrollY: 320,
      viewportHeight: 900,
      parentHeight: 720,
      size: 'middle',
      hasPagination: true,
    }).tableHeight).toBe(320);
  });
});
