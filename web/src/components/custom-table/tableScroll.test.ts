import { describe, expect, it } from 'vitest';
import { resolveTableScroll } from './tableScroll';

describe('resolveTableScroll fill width', () => {
  it('omits x when the pane is wider so columns can stretch instead of leaving a white gap', () => {
    expect(resolveTableScroll({
      calculatedScrollX: 900,
      containerWidth: 1280,
      scroll: { x: 'max-content', y: 'calc(100vh - 330px)' },
      calculatedScrollY: 400,
      hasData: true,
    }).x).toBeUndefined();
  });

  it('keeps column sum when columns overflow the container', () => {
    expect(resolveTableScroll({
      calculatedScrollX: 1600,
      containerWidth: 1000,
      scroll: { x: 'max-content' },
      calculatedScrollY: undefined,
      hasData: true,
    }).x).toBe(1600);
  });

  it('omits x for empty short tables so they still fill the pane', () => {
    expect(resolveTableScroll({
      calculatedScrollX: 900,
      containerWidth: 1280,
      scroll: { x: 'max-content' },
      calculatedScrollY: undefined,
      hasData: false,
    }).x).toBeUndefined();
  });

  it('leaves an explicit numeric x unchanged', () => {
    expect(resolveTableScroll({
      calculatedScrollX: 900,
      containerWidth: 1280,
      scroll: { x: 840, y: '400px' },
      calculatedScrollY: 400,
      hasData: true,
    }).x).toBe(840);
  });
});
