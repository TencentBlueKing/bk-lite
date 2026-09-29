import { describe, expect, it } from 'vitest';
import { resolveTableDimensions } from './tableHeight';

describe('resolveTableDimensions', () => {
  it('viewport calc taller than the drawer parent overflows the body', () => {
    const dimensions = resolveTableDimensions({
      scrollY: 'calc(100vh - 280px)',
      viewportHeight: 900,
      parentHeight: 480,
      size: 'middle',
      hasPagination: true,
    });
    expect(dimensions.containerHeight).toBeGreaterThan(480);
  });

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
