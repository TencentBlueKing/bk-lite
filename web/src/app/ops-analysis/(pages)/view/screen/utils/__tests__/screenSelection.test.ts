import { describe, expect, it } from 'vitest';
import { isSameScreenDataTarget } from '../screenSelection';

describe('isSameScreenDataTarget', () => {
  it('keeps the open data form when the selected widget is moved or clicked again', () => {
    expect(isSameScreenDataTarget('widget-1', 'widget-1')).toBe(true);
  });

  it('still guards a switch to another widget', () => {
    expect(isSameScreenDataTarget('widget-1', 'widget-2')).toBe(false);
  });

  it('still guards dismissing the selection', () => {
    expect(isSameScreenDataTarget('widget-1', null)).toBe(false);
  });

  it('still guards the first selection', () => {
    expect(isSameScreenDataTarget(null, 'widget-1')).toBe(false);
  });
});
