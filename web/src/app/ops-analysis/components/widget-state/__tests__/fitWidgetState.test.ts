import { describe, expect, it } from 'vitest';
import { toCanvasPixels } from '@/app/ops-analysis/components/widget-viewport';
import { fitWidgetStateContent } from '../fitWidgetState';

const fit = (
  width: number,
  height: number,
  scale = 1,
  textLength = 8,
) => fitWidgetStateContent({
  width,
  height,
  scale,
  textLength,
});

describe('fitWidgetStateContent', () => {
  it('drops the warning icon and shrinks the prompt when the component is small', () => {
    const small = fit(80, 64);
    const preferred = toCanvasPixels(13, 1);

    expect(small.showIcon).toBe(false);
    expect(small.fontSize).toBeLessThan(preferred);
    expect(small.fontSize * 1.25 * small.lineClamp).toBeLessThanOrEqual(64);
  });

  it('shrinks further as the component gets shorter', () => {
    const compact = fit(120, 96);
    const tiny = fit(120, 20);

    expect(tiny.showIcon).toBe(false);
    expect(tiny.fontSize).toBeLessThan(compact.fontSize);
    expect(tiny.fontSize * 1.25).toBeLessThanOrEqual(36);
  });

  it('keeps the normal prompt size and the warning icon when the component has room', () => {
    const roomy = fit(360, 200, 1, 12);

    expect(roomy.showIcon).toBe(true);
    expect(roomy.fontSize).toBe(toCanvasPixels(13, 1));
    expect(roomy.showTitle).toBe(false);
  });
});
