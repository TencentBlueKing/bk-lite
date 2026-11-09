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

  it('does not raise a measured numeric body height to the 160 floor', () => {
    expect(resolveTableDimensions({
      scrollY: 100,
      viewportHeight: 900,
      parentHeight: 180,
      size: 'small',
      hasPagination: false,
    })).toEqual({
      tableHeight: 100,
      containerHeight: 147,
    });
  });

  it('still raises a short pixel string so existing viewport estimates keep a usable body', () => {
    expect(resolveTableDimensions({
      scrollY: '80px',
      viewportHeight: 900,
      parentHeight: 180,
      size: 'small',
      hasPagination: false,
    }).tableHeight).toBe(160);
  });

  it('leaves an unpaginated table unconstrained when scroll.y is omitted', () => {
    expect(resolveTableDimensions({
      scrollY: undefined,
      viewportHeight: 900,
      parentHeight: 400,
      size: 'small',
      hasPagination: false,
    })).toEqual({
      tableHeight: undefined,
      containerHeight: undefined,
    });
  });
});
