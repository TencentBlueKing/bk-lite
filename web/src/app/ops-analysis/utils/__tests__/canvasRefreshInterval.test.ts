import { describe, expect, it } from 'vitest';
import {
  canPersistCanvasRefreshInterval,
  normalizeCanvasRefreshInterval,
} from '@/app/ops-analysis/utils/canvasRefreshInterval';

describe('normalizeCanvasRefreshInterval', () => {
  it.each([
    [undefined, 0],
    [null, 0],
    ['', 0],
    [60, 0],
    [1, 0],
    [0, 0],
    [60000, 60000],
    [300000, 300000],
    [600000, 600000],
    ['300000', 300000],
  ])('normalizes %s to %s', (raw, expected) => {
    expect(normalizeCanvasRefreshInterval(raw)).toBe(expected);
  });
});

describe('canPersistCanvasRefreshInterval', () => {
  it('persists only with edit permission on a non-builtin workbench canvas', () => {
    expect(
      canPersistCanvasRefreshInterval({
        shareMode: false,
        isBuiltIn: false,
        hasEditPermission: true,
      }),
    ).toBe(true);
  });

  it.each([
    [{ shareMode: true, isBuiltIn: false, hasEditPermission: true }],
    [{ shareMode: false, isBuiltIn: true, hasEditPermission: true }],
    [{ shareMode: false, isBuiltIn: false, hasEditPermission: false }],
  ])('does not persist %s', (options) => {
    expect(canPersistCanvasRefreshInterval(options)).toBe(false);
  });
});
