import { describe, expect, it } from 'vitest';
import { resolveRoom3DReadableScale } from '../readableScale';

describe('resolveRoom3DReadableScale', () => {
  it('drops the inverse fitScale compensation when geometry is already viewport pixels', () => {
    expect(resolveRoom3DReadableScale({
      enabled: true,
      fitScale: 0.5,
      widgetUiScale: 0.5,
      screenUiScale: 0.5,
      layoutMode: 'viewportPixels',
    })).toBe(0.5);
  });

  it('keeps the in-transform floor on the design canvas', () => {
    expect(resolveRoom3DReadableScale({
      enabled: true,
      fitScale: 0.5,
      widgetUiScale: 0.5,
      screenUiScale: 0.5,
    })).toBe(2);
  });
});
