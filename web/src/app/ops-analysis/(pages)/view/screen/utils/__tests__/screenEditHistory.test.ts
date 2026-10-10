import { describe, expect, it } from 'vitest';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { buildDefaultScreenViewSets } from '../viewport';
import { createScreenTextItem } from '../screenItems';
import {
  SCREEN_EDIT_HISTORY_LIMIT,
  closeScreenFieldEdit,
  commitScreenEdit,
  confirmScreenHistory,
  createScreenEditSession,
  redoScreenEdit,
  requestScreenHistory,
  screenHistoryShortcut,
  screenInspectorAfterReplace,
  screenItemFieldKey,
  screenViewportFieldKey,
  screenViewSetsAfterResizeStop,
  syncScreenEditInspector,
  undoScreenEdit,
  type ScreenEditDocument,
} from '../screenEditHistory';

const filter = (id: string): UnifiedFilterDefinition => ({
  id,
  key: id,
  name: id,
  type: 'string',
  order: 1,
  enabled: true,
});

const textAt = (content: string, x = 10, w = 100) =>
  createScreenTextItem([], { id: 'title', content, x, y: 20, w, h: 40, zIndex: 1 });

const documentWith = (
  content: string,
  x = 10,
  w = 100,
  filters: UnifiedFilterDefinition[] = [],
): ScreenEditDocument => {
  const viewSets = buildDefaultScreenViewSets();
  viewSets.items = [textAt(content, x, w)];
  viewSets.filters = filters;
  return { viewSets, filters };
};

const contentOf = (document: ScreenEditDocument) => {
  const item = document.viewSets.items[0];
  return item && 'content' in item ? item.content : '';
};

describe('screen edit history', () => {
  it('undoes one move and redoes it', () => {
    const session = createScreenEditSession(documentWith('标题', 10));
    const moved = commitScreenEdit(session, {
      document: documentWith('标题', 80),
      itemId: 'title',
    });

    expect(moved.canUndo).toBe(true);
    expect(moved.canRedo).toBe(false);
    expect(moved.document.viewSets.items[0]?.x).toBe(80);

    const undone = undoScreenEdit(moved);
    expect(undone.document.viewSets.items[0]?.x).toBe(10);
    expect(undone.canRedo).toBe(true);
    expect(redoScreenEdit(undone).document.viewSets.items[0]?.x).toBe(80);
  });

  it('undoes a delete back onto the item and clears selection when redo removes it', () => {
    const session = createScreenEditSession(documentWith('标题'), {
      selectedItemId: 'title',
      inspectorTab: 'data',
      dataConfigOpen: true,
    });
    const deleted = syncScreenEditInspector(
      commitScreenEdit(session, {
        document: {
          ...session.document,
          viewSets: { ...session.document.viewSets, items: [] },
        },
        itemId: 'title',
      }),
      { selectedItemId: null, inspectorTab: 'style', dataConfigOpen: false },
    );

    const restored = undoScreenEdit(deleted);
    expect(restored.document.viewSets.items.map((item) => item.id)).toEqual(['title']);
    expect(restored.inspector).toEqual({
      selectedItemId: 'title',
      inspectorTab: 'style',
      dataConfigOpen: false,
    });

    const removed = redoScreenEdit(restored);
    expect(removed.document.viewSets.items).toEqual([]);
    expect(removed.inspector.selectedItemId).toBeNull();
    expect(removed.inspector.dataConfigOpen).toBe(false);
  });

  it('restores both size and position with one undo after a resize stop', () => {
    const session = createScreenEditSession(documentWith('标题', 10, 100));
    const placed = screenViewSetsAfterResizeStop(
      session.document.viewSets,
      'title',
      { w: 180, h: 90 },
      { x: 40, y: 24 },
    );
    const committed = commitScreenEdit(session, {
      document: { ...session.document, viewSets: placed },
      itemId: 'title',
    });

    expect(committed.document.viewSets.items[0]).toMatchObject({ x: 40, y: 24, w: 180, h: 90 });
    const undone = undoScreenEdit(committed);
    expect(undone.document.viewSets.items[0]).toMatchObject({
      x: 10,
      y: 20,
      w: 100,
      h: 40,
    });
    expect(undone.canUndo).toBe(false);
  });

  it('coalesces continuous edits of the same field until the field closes', () => {
    const session = createScreenEditSession(documentWith(''));
    const first = documentWith('运');
    const second = documentWith('运营');
    const fieldKey = screenItemFieldKey(
      session.document.viewSets.items[0],
      first.viewSets.items[0],
    );
    const typed = commitScreenEdit(
      commitScreenEdit(session, { document: first, itemId: 'title', fieldKey: fieldKey ?? undefined }),
      { document: second, itemId: 'title', fieldKey: fieldKey ?? undefined },
    );

    expect(fieldKey).toBe('content');
    expect(contentOf(undoScreenEdit(typed).document)).toBe('');
    expect(undoScreenEdit(typed).canUndo).toBe(false);

    const closed = closeScreenFieldEdit(typed);
    const nextBurst = commitScreenEdit(closed, {
      document: documentWith('运营分析'),
      itemId: 'title',
      fieldKey: 'content',
    });
    expect(contentOf(undoScreenEdit(nextBurst).document)).toBe('运营');
    expect(contentOf(undoScreenEdit(undoScreenEdit(nextBurst)).document)).toBe('');
  });

  it('drops redo after a new gesture, including another edit of an open field', () => {
    const session = createScreenEditSession(documentWith('A'));
    const first = commitScreenEdit(session, {
      document: documentWith('AB'),
      itemId: 'title',
      fieldKey: 'content',
    });
    const undone = undoScreenEdit(first);
    const editedAgain = commitScreenEdit(undone, {
      document: documentWith('AC'),
      itemId: 'title',
      fieldKey: 'content',
    });

    expect(editedAgain.canRedo).toBe(false);
    expect(contentOf(redoScreenEdit(editedAgain).document)).toBe('AC');
    expect(contentOf(undoScreenEdit(editedAgain).document)).toBe('A');
  });

  it('keeps only the latest 50 steps', () => {
    let session = createScreenEditSession(documentWith('标题', 0));
    for (let step = 1; step <= SCREEN_EDIT_HISTORY_LIMIT + 1; step += 1) {
      session = commitScreenEdit(session, {
        document: documentWith('标题', step),
        itemId: 'title',
      });
    }

    for (let count = 0; count < SCREEN_EDIT_HISTORY_LIMIT; count += 1) {
      session = undoScreenEdit(session);
    }
    expect(session.document.viewSets.items[0]?.x).toBe(1);
    expect(session.canUndo).toBe(false);
  });

  it('records a filter confirm or snapshot restore as one whole-document step', () => {
    const start = createScreenEditSession(documentWith('标题', 10, 100, [filter('env')]), {
      selectedItemId: 'title',
      inspectorTab: 'style',
      dataConfigOpen: false,
    });
    const confirmed = commitScreenEdit(start, {
      document: documentWith('标题', 10, 100, [filter('region')]),
    });
    expect(undoScreenEdit(confirmed).document.filters.map((item) => item.id)).toEqual(['env']);
    expect(undoScreenEdit(confirmed).inspector.selectedItemId).toBe('title');

    const restored = commitScreenEdit(confirmed, {
      document: {
        viewSets: buildDefaultScreenViewSets(),
        filters: [],
      },
    });
    expect(screenInspectorAfterReplace(restored.inspector, restored.document)).toEqual({
      selectedItemId: null,
      inspectorTab: 'style',
      dataConfigOpen: false,
    });
    const cleared = syncScreenEditInspector(restored, {
      selectedItemId: null,
      inspectorTab: 'style',
      dataConfigOpen: false,
    });
    const back = undoScreenEdit(cleared);
    expect(back.document.viewSets.items.map((item) => item.id)).toEqual(['title']);
    expect(back.inspector.selectedItemId).toBeNull();
    expect(undoScreenEdit(back).document.filters.map((item) => item.id)).toEqual(['env']);
  });

  it('leaves history unchanged when the document is unchanged', () => {
    const session = createScreenEditSession(documentWith('标题', 10));
    const moved = commitScreenEdit(session, {
      document: documentWith('标题', 30),
      itemId: 'title',
    });
    const saved = commitScreenEdit(moved, { document: moved.document });

    expect(saved.canUndo).toBe(true);
    expect(undoScreenEdit(saved).document.viewSets.items[0]?.x).toBe(10);
  });

  it('selects the item a step touched and keeps the inspector tab when it was already selected', () => {
    const session = createScreenEditSession(documentWith('标题', 10), {
      selectedItemId: 'title',
      inspectorTab: 'data',
      dataConfigOpen: true,
    });
    const moved = commitScreenEdit(session, {
      document: documentWith('标题', 50),
      itemId: 'title',
    });
    const afterMove = undoScreenEdit(moved);
    expect(afterMove.inspector).toEqual({
      selectedItemId: 'title',
      inspectorTab: 'data',
      dataConfigOpen: true,
    });

    const otherSelected = undoScreenEdit(syncScreenEditInspector(moved, {
      selectedItemId: null,
      inspectorTab: 'style',
      dataConfigOpen: false,
    }));
    expect(otherSelected.inspector.selectedItemId).toBe('title');
    expect(otherSelected.inspector.inspectorTab).toBe('style');
    expect(otherSelected.inspector.dataConfigOpen).toBe(false);
  });

  it('asks before discarding an unapplied data form and applies history only after confirm', () => {
    const session = commitScreenEdit(createScreenEditSession(documentWith('前')), {
      document: documentWith('后'),
      itemId: 'title',
    });
    const blocked = requestScreenHistory(session, 'undo', true);

    expect(blocked.needsConfirm).toBe(true);
    if (!blocked.needsConfirm) return;
    expect(contentOf(blocked.session.document)).toBe('后');

    const applied = confirmScreenHistory(blocked.session, 'undo');
    expect(contentOf(applied.document)).toBe('前');
    expect(contentOf(requestScreenHistory(session, 'undo', false).session.document)).toBe('前');
  });

  it('ignores history shortcuts in the filter bar and in modals', () => {
    const filterInput = document.createElement('input');
    const filterBar = document.createElement('div');
    filterBar.setAttribute('data-ops-analysis-filter-bar', '');
    filterBar.append(filterInput);
    const modalInput = document.createElement('input');
    const modal = document.createElement('div');
    modal.className = 'ant-modal';
    modal.append(modalInput);
    const styleInput = document.createElement('textarea');
    document.body.append(filterBar, modal, styleInput);

    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: filterInput,
    }, true)).toBeNull();
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: modalInput,
    }, true)).toBeNull();
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: styleInput,
    }, true)).toBe('undo');
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: false, metaKey: true, shiftKey: false, target: styleInput,
    }, true)).toBeNull();
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: true, target: styleInput,
    }, true)).toBeNull();
    expect(screenHistoryShortcut({
      key: 'y', ctrlKey: true, metaKey: false, shiftKey: false, target: styleInput,
    }, true)).toBe('redo');
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: styleInput,
    }, false)).toBeNull();

    const popup = document.createElement('div');
    popup.className = 'ant-select-dropdown';
    const list = document.createElement('div');
    list.id = 'filter-popup_list';
    const trigger = document.createElement('input');
    trigger.setAttribute('aria-controls', 'filter-popup_list');
    filterBar.append(trigger);
    const option = document.createElement('div');
    list.append(option);
    popup.append(list);
    const inspectorPopup = document.createElement('div');
    inspectorPopup.id = 'style-popup';
    inspectorPopup.className = 'ant-select-dropdown';
    const inspectorOption = document.createElement('div');
    inspectorPopup.append(inspectorOption);
    document.body.append(popup, inspectorPopup);

    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: option,
    }, true)).toBeNull();
    expect(screenHistoryShortcut({
      key: 'z', ctrlKey: true, metaKey: false, shiftKey: false, target: inspectorOption,
    }, true)).toBe('undo');

    filterBar.remove();
    modal.remove();
    styleInput.remove();
    popup.remove();
    inspectorPopup.remove();
  });

  it('records adding an item as one step', () => {
    const session = createScreenEditSession(documentWith('标题'));
    const added = commitScreenEdit(session, {
      document: {
        ...session.document,
        viewSets: {
          ...session.document.viewSets,
          items: [...session.document.viewSets.items, textAt('新组件', 40)],
        },
      },
    });

    expect(undoScreenEdit(added).document.viewSets.items).toHaveLength(1);
    expect(added.canUndo).toBe(true);
    expect(undoScreenEdit(undoScreenEdit(added)).canUndo).toBe(false);
  });

  it('starts a new step when the field changes or a drag begins', () => {
    const session = createScreenEditSession(documentWith(''));
    const contentKey = screenItemFieldKey(
      session.document.viewSets.items[0],
      documentWith('运').viewSets.items[0],
    );
    const typed = commitScreenEdit(session, {
      document: documentWith('运'),
      itemId: 'title',
      fieldKey: contentKey ?? undefined,
    });
    const movedWhileOpen = commitScreenEdit(typed, {
      document: documentWith('运', 80),
      itemId: 'title',
    });

    expect(undoScreenEdit(movedWhileOpen).document.viewSets.items[0]?.x).toBe(10);
    expect(contentOf(undoScreenEdit(undoScreenEdit(movedWhileOpen)).document)).toBe('');

    const xKey = screenItemFieldKey(
      documentWith('运').viewSets.items[0],
      documentWith('运', 30).viewSets.items[0],
    );
    const typedX = commitScreenEdit(typed, {
      document: documentWith('运', 30),
      itemId: 'title',
      fieldKey: xKey ?? undefined,
    });
    const typedXAgain = commitScreenEdit(typedX, {
      document: documentWith('运', 36),
      itemId: 'title',
      fieldKey: xKey ?? undefined,
    });
    const centered = commitScreenEdit(closeScreenFieldEdit(typedXAgain), {
      document: documentWith('运', 200),
      itemId: 'title',
      fieldKey: xKey ?? undefined,
    });

    expect(undoScreenEdit(centered).document.viewSets.items[0]?.x).toBe(36);
    expect(undoScreenEdit(undoScreenEdit(centered)).document.viewSets.items[0]?.x).toBe(10);
  });

  it('keeps canvas width edits as the open step until the field closes', () => {
    const session = createScreenEditSession(documentWith('标题'));
    const wider = {
      ...session.document,
      viewSets: {
        ...session.document.viewSets,
        viewport: { ...session.document.viewSets.viewport, width: 2000 },
      },
    };
    const widerStill = {
      ...wider,
      viewSets: {
        ...wider.viewSets,
        viewport: { ...wider.viewSets.viewport, width: 2100 },
      },
    };
    const fieldKey = screenViewportFieldKey(
      session.document.viewSets.viewport,
      wider.viewSets.viewport,
    );
    const typed = commitScreenEdit(
      commitScreenEdit(session, { document: wider, fieldKey: fieldKey ?? undefined }),
      { document: widerStill, fieldKey: fieldKey ?? undefined },
    );

    expect(undoScreenEdit(typed).document.viewSets.viewport.width).toBe(
      session.document.viewSets.viewport.width,
    );
    expect(undoScreenEdit(typed).canUndo).toBe(false);
  });

  it('keeps edge-clamped geometry on the field being typed', () => {
    const before = documentWith('标题', 10, 100);
    const item = before.viewSets.items[0];
    const once = {
      ...before,
      viewSets: {
        ...before.viewSets,
        items: [{ ...item, w: 1800, x: 120 }],
      },
    };
    const twice = {
      ...before,
      viewSets: {
        ...before.viewSets,
        items: [{ ...item, w: 1810, x: 110 }],
      },
    };
    expect(screenItemFieldKey(item, once.viewSets.items[0], 'w')).toBe('w');

    const typed = commitScreenEdit(
      commitScreenEdit(createScreenEditSession(before), {
        document: once,
        itemId: 'title',
        fieldKey: 'w',
      }),
      { document: twice, itemId: 'title', fieldKey: 'w' },
    );

    expect(undoScreenEdit(typed).document.viewSets.items[0]?.w).toBe(100);
    expect(undoScreenEdit(typed).document.viewSets.items[0]?.x).toBe(10);
    expect(undoScreenEdit(typed).canUndo).toBe(false);
  });
});
