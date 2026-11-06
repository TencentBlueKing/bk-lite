import { describe, expect, it } from 'vitest';
import { CAROUSEL_MAX_ITEMS } from '@/app/ops-analysis/utils/carouselPlayer';
import {
  canvasIdentityKey,
  carouselRoundSeconds,
  displayedMoveTarget,
  duplicateCanvasKeys,
  mergeCanvasChecks,
  remainingCapacity,
  sameCarouselDraft,
  selectionChangeCounts,
  shouldShowRemainingCapacity,
  syncCarouselSelection,
} from '@/app/ops-analysis/utils/carouselDraft';

interface Row {
  key: string;
  resourceType: string;
  canvasId: number;
  dwellSeconds: number | null;
}

const row = (canvasId: number, dwellSeconds: number | null = null, resourceType = 'dashboard'): Row => ({
  key: `${resourceType}-${canvasId}-${dwellSeconds ?? 'default'}`,
  resourceType,
  canvasId,
  dwellSeconds,
});

const canvas = (canvasId: number, resourceType = 'dashboard') => ({ resourceType, canvasId, name: String(canvasId) });

describe('carousel draft selection', () => {
  it('appends new canvases, removes unchecked ones, and keeps order and dwell', () => {
    const current = [row(1, 12), row(2, null), row(3, 40)];
    const selected = [canvas(1), canvas(3), canvas(4), canvas(5)];
    const result = syncCarouselSelection(
      current,
      selected,
      ['dashboard:1', 'dashboard:2', 'dashboard:3', 'dashboard:4', 'dashboard:5'],
      (item) => canvasIdentityKey(item.resourceType, item.canvasId),
      (item) => row(item.canvasId, 7),
    );
    expect(result.added).toBe(2);
    expect(result.removed).toBe(1);
    expect(result.items.map((item) => [item.canvasId, item.dwellSeconds])).toEqual([
      [1, 12],
      [3, 40],
      [4, 7],
      [5, 7],
    ]);
  });

  it('does not add a canvas that is already in the list', () => {
    const current = [row(1, 9), row(1, 15)];
    const result = syncCarouselSelection(
      current,
      [canvas(1), canvas(1)],
      ['dashboard:1'],
      (item) => canvasIdentityKey(item.resourceType, item.canvasId),
      (item) => row(item.canvasId, null),
    );
    expect(result.added).toBe(0);
    expect(result.removed).toBe(0);
    expect(result.items).toEqual(current);
    expect(duplicateCanvasKeys(current)).toEqual(['dashboard:1']);
  });

  it('counts row removals when a duplicated canvas is unchecked', () => {
    const current = [row(1), row(1), row(2, 20)];
    expect(selectionChangeCounts(
      current.map((item) => ({ resourceType: item.resourceType, canvasId: item.canvasId })),
      ['dashboard:2'],
      ['dashboard:1', 'dashboard:2'],
    )).toEqual({ added: 0, removed: 2, selected: 1 });
  });

  it('keeps rows the directory tree does not contain, including a removed pending add', () => {
    const hidden = row(9, 15);
    const kept = row(1, 12);
    const result = syncCarouselSelection(
      [kept, hidden],
      [canvas(3)],
      ['dashboard:1', 'dashboard:3'],
      (item) => canvasIdentityKey(item.resourceType, item.canvasId),
      (item) => row(item.canvasId, null),
    );
    expect(result.removed).toBe(1);
    expect(result.added).toBe(1);
    expect(result.items.map((item) => [item.canvasId, item.dwellSeconds])).toEqual([
      [9, 15],
      [3, null],
    ]);
    expect(result.items[0]).toBe(hidden);

    const pendingRemoved = syncCarouselSelection(
      [kept],
      [canvas(1)],
      ['dashboard:1', 'dashboard:8'],
      (item) => canvasIdentityKey(item.resourceType, item.canvasId),
      (item) => row(item.canvasId, null),
    );
    expect(pendingRemoved.items).toEqual([kept]);
    expect(pendingRemoved.added).toBe(0);
    expect(pendingRemoved.removed).toBe(0);

    const failedTree = syncCarouselSelection(
      [kept, hidden],
      [],
      [],
      (item) => canvasIdentityKey(item.resourceType, item.canvasId),
      (item) => row(item.canvasId, null),
    );
    expect(failedTree.items).toEqual([kept, hidden]);
    expect(failedTree.removed).toBe(0);
  });

  it('moves up and down by the displayed order and maps back to the full list', () => {
    expect(displayedMoveTarget([0, 2, 5], 1, -1)).toBe(0);
    expect(displayedMoveTarget([0, 2, 5], 1, 1)).toBe(5);
    expect(displayedMoveTarget([0, 2, 5], 0, -1)).toBeNull();
    expect(displayedMoveTarget([0, 2, 5], 2, 1)).toBeNull();
  });

  it('treats a draft as clean when order, dwell and fields match the snapshot', () => {
    const saved = {
      name: '值班',
      desc: '',
      groups: [2, 1],
      defaultDwell: 30,
      items: [{ resourceType: 'dashboard', canvasId: 9, dwellSeconds: 15 }],
    };
    expect(sameCarouselDraft(saved, {
      ...saved,
      groups: [1, 2],
    })).toBe(true);
    expect(sameCarouselDraft(saved, {
      ...saved,
      items: [{ resourceType: 'dashboard', canvasId: 9, dwellSeconds: 16 }],
    })).toBe(false);
  });

  it('blocks a directory check that would pass the 50 canvas limit', () => {
    const current = Array.from({ length: 49 }, (_, index) => `dashboard:${index + 1}`);
    const visible = ['dashboard:50', 'dashboard:51'];
    const blocked = mergeCanvasChecks(current, visible, visible);
    expect(blocked.blocked).toBe(true);
    expect(blocked.keys).toEqual(current);

    const oneMore = mergeCanvasChecks(current, ['dashboard:50'], ['dashboard:50']);
    expect(oneMore.blocked).toBe(false);
    expect(oneMore.keys).toHaveLength(50);

    const hiddenKept = mergeCanvasChecks(
      ['screen:1', 'dashboard:2'],
      ['dashboard:2', 'dashboard:3'],
      ['dashboard:3'],
    );
    expect(hiddenKept.blocked).toBe(false);
    expect(hiddenKept.keys).toEqual(['screen:1', 'dashboard:3']);
  });

  it('shows remaining capacity only near the limit', () => {
    expect(shouldShowRemainingCapacity(30)).toBe(false);
    expect(shouldShowRemainingCapacity(CAROUSEL_MAX_ITEMS - 10)).toBe(true);
    expect(shouldShowRemainingCapacity(CAROUSEL_MAX_ITEMS)).toBe(true);
    expect(remainingCapacity(CAROUSEL_MAX_ITEMS - 3)).toBe(3);
  });

  it('sums dwell from valid canvases and skips invalid ones', () => {
    expect(carouselRoundSeconds([
      { dwellSeconds: 10, countsTowardDuration: true },
      { dwellSeconds: null, countsTowardDuration: true },
      { dwellSeconds: 300, countsTowardDuration: false },
    ], 30)).toBe(40);
  });
});
