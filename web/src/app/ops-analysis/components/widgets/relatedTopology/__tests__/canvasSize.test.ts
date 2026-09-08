import { describe, expect, it } from 'vitest';
import { canvasBoxChanged, readStableCanvasBox } from '../canvasSize';

describe('related topology canvas size', () => {
  it('ignores sub-pixel jitter and unchanged boxes', () => {
    expect(canvasBoxChanged({ width: 640, height: 360 }, { width: 640, height: 360 })).toBe(
      false,
    );
    expect(canvasBoxChanged(null, { width: 640, height: 360 })).toBe(true);
    expect(canvasBoxChanged({ width: 640, height: 360 }, { width: 639, height: 360 })).toBe(
      true,
    );
  });

  it('rejects an unlaid-out host so X6 cannot mount at 0 and thrash', () => {
    const host = document.createElement('div');
    Object.defineProperties(host, {
      clientWidth: { configurable: true, get: () => 0 },
      clientHeight: { configurable: true, get: () => 280 },
    });
    expect(readStableCanvasBox(host)).toBeNull();
  });
});
