import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import {
  loadPlaybackCanvasDetail,
  type PlaybackInitialDetail,
} from '@/app/ops-analysis/context/playbackInitialDetail';
import { clearCanvasDetailCache } from '@/app/ops-analysis/utils/canvasDetailCache';
import { shouldRunCanvasIntervalTick } from '@/app/ops-analysis/utils/canvasRefreshTimer';

const TYPES: CanvasType[] = [
  'dashboard',
  'topology',
  'architecture',
  'screen',
  'report',
  'networkTopology',
];

const seed = (resourceType: CanvasType, detail: unknown): PlaybackInitialDetail => ({
  resourceType,
  canvasId: 7,
  detail,
});

describe('playback initial detail', () => {
  beforeEach(() => {
    clearCanvasDetailCache();
  });

  it('serves the confirmed detail for every canvas type and does not fetch again', async () => {
    for (const resourceType of TYPES) {
      const fetchDetail = vi.fn(async () => ({ refresh_interval: 1 }));
      const detail = { id: 7, refresh_interval: 60_000, name: resourceType };
      const first = await loadPlaybackCanvasDetail(seed(resourceType, detail), resourceType, '7', fetchDetail);
      const second = await loadPlaybackCanvasDetail(seed(resourceType, detail), resourceType, 7, fetchDetail);
      expect(first).toBe(detail);
      expect(second).toBe(detail);
      expect(fetchDetail).not.toHaveBeenCalled();
    }
  });

  it('fetches when playback has no seed or the seed is for another canvas', async () => {
    const fetchDetail = vi.fn(async () => ({ refresh_interval: 30_000 }));
    const first = await loadPlaybackCanvasDetail(null, 'dashboard', 7, fetchDetail);
    const second = await loadPlaybackCanvasDetail(seed('topology', { id: 7 }), 'dashboard', 7, fetchDetail);
    const third = await loadPlaybackCanvasDetail(seed('dashboard', { id: 8 }), 'dashboard', 9, fetchDetail);
    expect(second).toBe(first);
    expect(third).toEqual({ refresh_interval: 30_000 });
    expect(fetchDetail).toHaveBeenCalledTimes(2);
  });

  it('keeps refresh interval behavior on the confirmed payload', () => {
    const off = { refresh_interval: 0 };
    const on = { refresh_interval: 60_000 };
    expect(shouldRunCanvasIntervalTick({
      effectiveIntervalMs: off.refresh_interval,
      documentHidden: false,
    })).toBe(false);
    expect(shouldRunCanvasIntervalTick({
      effectiveIntervalMs: on.refresh_interval,
      documentHidden: false,
    })).toBe(true);
  });
});
