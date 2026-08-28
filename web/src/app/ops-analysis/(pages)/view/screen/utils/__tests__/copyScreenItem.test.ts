import { describe, expect, it, vi } from 'vitest';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import { createScreenCopyItemHandler } from '../copyScreenItem';

const viewSets: ScreenViewSets = {
  viewport: { width: 1920, height: 1080 },
  decorations: {},
  items: [
    {
      id: 'line-1',
      type: 'widget',
      chartType: 'line',
      title: 'CPU',
      x: 100,
      y: 80,
      w: 400,
      h: 240,
      zIndex: 2,
      valueConfig: { chartType: 'line', dataSource: 42 },
    },
  ],
};

describe('createScreenCopyItemHandler', () => {
  it('selects the new widget even when the draft updater has not run yet', () => {
    const setDraftViewSets = vi.fn();
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      setDraftViewSets,
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'line-copy',
    });

    handleCopyItem('line-1');

    expect(setSelectedItemId).toHaveBeenCalledWith('line-copy');
    expect(setDraftViewSets).toHaveBeenCalledTimes(1);
    expect(setDraftViewSets.mock.calls[0][0]).toEqual(expect.any(Function));
  });

  it('applies the copy onto a queued draft and selects that same new id', () => {
    let draft = viewSets;
    const setDraftViewSets = (
      updater: ScreenViewSets | ((current: ScreenViewSets) => ScreenViewSets),
    ) => {
      draft = typeof updater === 'function' ? updater(draft) : updater;
    };
    let selectedItemId: string | null = 'line-1';
    const handleCopyItem = createScreenCopyItemHandler({
      setDraftViewSets,
      setSelectedItemId: (next) => {
        selectedItemId = typeof next === 'function' ? next(selectedItemId) : next;
      },
      rebuildFilters: (next) => next,
      createId: () => 'line-copy',
    });

    setDraftViewSets((current) => ({
      ...current,
      decorations: { title: 'queued' },
    }));
    handleCopyItem('line-1');

    expect(selectedItemId).toBe('line-copy');
    expect(draft.decorations.title).toBe('queued');
    expect(draft.items.map((item) => item.id)).toEqual(['line-1', 'line-copy']);
  });
});
