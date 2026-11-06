import { describe, expect, it } from 'vitest';
import type { PlaybackSlide } from '@/app/ops-analysis/components/carousel/playbackCanvas';
import {
  playbackCanvasKey,
  playbackShellKey,
  reducePlaybackFrameError,
  resolvePlaybackStage,
  type HeldPlaybackFrame,
} from '@/app/ops-analysis/components/carousel/playbackStage';

const TYPES = [
  'dashboard',
  'topology',
  'architecture',
  'screen',
  'report',
  'networkTopology',
] as const;

const slide = (
  resourceType: PlaybackSlide['resourceType'],
  canvasId: number,
  available = true,
): PlaybackSlide => ({
  key: `${resourceType}-${canvasId}`,
  resourceType,
  canvasId,
  name: `${resourceType}-${canvasId}`,
  dwellSeconds: 30,
  available,
});

describe('resolvePlaybackStage', () => {
  it('keeps shell identity on the resource type and remounts the canvas when its id changes', () => {
    expect(playbackShellKey('dashboard')).toBe('dashboard');
    expect(playbackCanvasKey(slide('dashboard', 4))).toBe('dashboard:4');
    expect(playbackCanvasKey(slide('dashboard', 9))).toBe('dashboard:9');
    expect(playbackShellKey('screen')).not.toBe(playbackShellKey('dashboard'));
  });

  it.each(TYPES)(
    'paints a cached %s immediately and holds the previous frame of the same type when the cache misses',
    (resourceType) => {
      const current = slide(resourceType, 1);
      const next = slide(resourceType, 2);
      const other = slide(resourceType === 'screen' ? 'dashboard' : 'screen', 3);
      const held: HeldPlaybackFrame = { slide: current, detail: { id: 1, view_sets: { kept: true } } };

      const cached = resolvePlaybackStage({
        slide: next,
        ready: false,
        confirmedDetail: undefined,
        cached: { hit: true, detail: { id: 2, view_sets: { fresh: true } } },
        held,
      });
      expect(cached).toMatchObject({
        kind: 'frame',
        holding: false,
        shellKey: resourceType,
        canvasKey: `${resourceType}:2`,
        detail: { id: 2, view_sets: { fresh: true } },
      });
      if (cached.kind === 'frame') {
        expect(cached.slide.canvasId).toBe(2);
      }

      const waiting = resolvePlaybackStage({
        slide: next,
        ready: false,
        confirmedDetail: undefined,
        cached: { hit: false },
        held,
      });
      expect(waiting).toMatchObject({
        kind: 'frame',
        holding: true,
        shellKey: resourceType,
        canvasKey: `${resourceType}:1`,
      });
      if (waiting.kind === 'frame') {
        expect(waiting.slide).toBe(current);
      }

      const crossType = resolvePlaybackStage({
        slide: other,
        ready: false,
        confirmedDetail: undefined,
        cached: { hit: false },
        held,
      });
      expect(crossType).toEqual({ kind: 'pending' });
    },
  );

  it('drops the held frame when the target slide is unavailable', () => {
    const held: HeldPlaybackFrame = {
      slide: slide('topology', 8),
      detail: { id: 8 },
    };
    expect(resolvePlaybackStage({
      slide: slide('topology', 9, false),
      ready: false,
      confirmedDetail: undefined,
      cached: { hit: true, detail: { id: 9 } },
      held,
    })).toEqual({ kind: 'unavailable' });
  });

  it('releases a held frame that errors instead of swallowing it into a blank wall', () => {
    expect(reducePlaybackFrameError(true, 'dashboard-1')).toEqual({ type: 'release-hold' });
    expect(reducePlaybackFrameError(false, 'dashboard-2')).toEqual({
      type: 'mark-unavailable',
      key: 'dashboard-2',
    });
    expect(reducePlaybackFrameError(false, '')).toBeNull();
  });

  it('prefers the confirmed detail once the slide is ready', () => {
    const target = slide('architecture', 5);
    const stage = resolvePlaybackStage({
      slide: target,
      ready: true,
      confirmedDetail: { id: 5, source: 'confirm' },
      cached: { hit: true, detail: { id: 5, source: 'cache' } },
      held: null,
    });
    expect(stage).toMatchObject({
      kind: 'frame',
      holding: false,
      detail: { id: 5, source: 'confirm' },
      shellKey: 'architecture',
      canvasKey: 'architecture:5',
    });
  });
});
