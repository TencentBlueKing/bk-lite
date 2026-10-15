import { describe, expect, it, vi } from 'vitest';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import { createScreenShapeItem, createScreenTextItem } from '../screenItems';
import { copyScreenChromeItem, createScreenCopyItemHandler } from '../copyScreenItem';

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

const sceneViewSets: ScreenViewSets = {
  ...viewSets,
  items: [
    {
      id: 'topo-1',
      type: 'widget',
      chartType: 'networkStatusTopology',
      title: '网络拓扑',
      x: 100,
      y: 80,
      w: 400,
      h: 240,
      zIndex: 2,
      valueConfig: {
        chartType: 'networkStatusTopology',
        sceneWidgetType: 'networkStatusTopology',
      },
    },
  ],
};

const applyDraft = (
  draft: { current: ScreenViewSets },
): ((
  updater: ScreenViewSets | ((current: ScreenViewSets) => ScreenViewSets),
) => void) => {
  return (updater) => {
    draft.current =
      typeof updater === 'function' ? updater(draft.current) : updater;
  };
};

describe('createScreenCopyItemHandler', () => {
  it('selects the new widget even when the draft updater has not run yet', () => {
    const setDraftViewSets = vi.fn();
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => viewSets,
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
      getDraftViewSets: () => draft,
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

  it('does not select or insert when the source is a scene widget', () => {
    const draft = { current: sceneViewSets };
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => draft.current,
      setDraftViewSets: applyDraft(draft),
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'topo-copy',
    });

    handleCopyItem('topo-1');

    expect(setSelectedItemId).not.toHaveBeenCalled();
    expect(draft.current.items.map((item) => item.id)).toEqual(['topo-1']);
  });

  it('does not select or insert when the source id is missing', () => {
    const draft = { current: viewSets };
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => draft.current,
      setDraftViewSets: applyDraft(draft),
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'ghost-copy',
    });

    handleCopyItem('missing');

    expect(setSelectedItemId).not.toHaveBeenCalled();
    expect(draft.current.items.map((item) => item.id)).toEqual(['line-1']);
  });

  it('does not select a scene widget even when the draft updater has not run yet', () => {
    const setDraftViewSets = vi.fn();
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => sceneViewSets,
      setDraftViewSets,
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'topo-copy',
    });

    handleCopyItem('topo-1');

    expect(setSelectedItemId).not.toHaveBeenCalled();
    expect(setDraftViewSets).not.toHaveBeenCalled();
  });

  it('does not select when a pending draft update already removed the source', () => {
    const lastRender = viewSets;
    const pending = { ...viewSets, items: [] as ScreenViewSets['items'] };
    let draft = pending;
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => lastRender,
      setDraftViewSets: (updater) => {
        draft = typeof updater === 'function' ? updater(draft) : updater;
      },
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'line-copy',
    });

    handleCopyItem('line-1');

    expect(setSelectedItemId).not.toHaveBeenCalled();
    expect(draft.items.map((item) => item.id)).toEqual([]);
  });

  it('copies chrome beside the source, on top, without changing its content', () => {
    const text = createScreenTextItem([], {
      id: 'text-1',
      content: '说明',
      x: 100,
      y: 80,
      w: 200,
      h: 40,
      zIndex: 2,
    });
    const shape = createScreenShapeItem([text], 'rect', {
      id: 'shape-1',
      x: 1900,
      y: 1000,
      w: 80,
      h: 40,
      zIndex: 3,
    });
    const draft = {
      current: {
        ...viewSets,
        items: [text, shape],
      } satisfies ScreenViewSets,
    };
    const setSelectedItemId = vi.fn();
    const handleCopyItem = createScreenCopyItemHandler({
      getDraftViewSets: () => draft.current,
      setDraftViewSets: applyDraft(draft),
      setSelectedItemId,
      rebuildFilters: (next) => next,
      createId: () => 'text-copy',
    });

    handleCopyItem('text-1');

    expect(setSelectedItemId).toHaveBeenCalledWith('text-copy');
    const copied = draft.current.items.find((item) => item.id === 'text-copy');
    expect(copied).toMatchObject({
      content: '说明',
      x: 148,
      y: 128,
      w: 200,
      h: 40,
      zIndex: 4,
    });
    if (copied && 'textStyle' in copied && 'textStyle' in text) {
      copied.textStyle.fontSize = 99;
      expect(text.textStyle.fontSize).not.toBe(99);
    }

    const shapeCopy = copyScreenChromeItem(draft.current, 'shape-1', {
      createId: () => 'shape-copy',
    });
    const placed = shapeCopy?.viewSets.items.find((item) => item.id === 'shape-copy');
    expect(placed).toMatchObject({
      shape: 'rect',
      x: 1840,
      y: 1040,
      zIndex: 5,
    });
  });
});
