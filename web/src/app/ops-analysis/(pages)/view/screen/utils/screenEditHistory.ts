import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type {
  ScreenItem,
  ScreenTextItem,
  ScreenViewSets,
  ScreenViewportConfig,
} from '@/app/ops-analysis/types/screen';
import { moveScreenItem, resizeScreenItem } from './layoutUtils';
import { isScreenShapeItem, isScreenTextItem, isScreenTitleFrameItem } from './screenItems';

export const SCREEN_EDIT_HISTORY_LIMIT = 50;

const SHORTCUT_BLOCK_SELECTOR = '.ant-modal, [data-ops-analysis-filter-bar]';
const FILTER_POPUP_SELECTOR = '.ant-select-dropdown, .ant-picker-dropdown, .ant-cascader-dropdown, .ant-tree-select-dropdown';

const popupOwnedByBlockedTrigger = (target: Element): boolean => {
  if (typeof document === 'undefined') return false;
  const popup = target.closest(FILTER_POPUP_SELECTOR);
  if (!popup) return false;
  const ids = new Set<string>();
  if (popup.id) ids.add(popup.id);
  popup.querySelectorAll('[id]').forEach((node) => {
    if (node.id) ids.add(node.id);
  });
  for (const id of ids) {
    const trigger = document.querySelector(`[aria-controls~="${CSS.escape(id)}"]`);
    if (trigger?.closest(SHORTCUT_BLOCK_SELECTOR)) return true;
  }
  return false;
};

const shortcutBlocked = (target: EventTarget | null): boolean => {
  if (!(target instanceof Element)) return false;
  if (target.closest(SHORTCUT_BLOCK_SELECTOR)) return true;
  return popupOwnedByBlockedTrigger(target);
};

export interface ScreenEditDocument {
  viewSets: ScreenViewSets;
  filters: UnifiedFilterDefinition[];
}

export interface ScreenEditInspector {
  selectedItemId: string | null;
  inspectorTab: 'style' | 'data';
  dataConfigOpen: boolean;
}

export interface ScreenEditSession {
  document: ScreenEditDocument;
  inspector: ScreenEditInspector;
  canUndo: boolean;
  canRedo: boolean;
}

export interface ScreenEditCommit {
  document: ScreenEditDocument;
  itemId?: string;
  fieldKey?: string;
}

interface HistoryEntry {
  before: ScreenEditDocument;
  after: ScreenEditDocument;
  itemId: string | null;
  fieldKey: string | null;
}

interface HistoryStore {
  past: HistoryEntry[];
  future: HistoryEntry[];
  openField: { itemId: string | null; fieldKey: string } | null;
}

const stores = new WeakMap<ScreenEditSession, HistoryStore>();

const emptyInspector = (): ScreenEditInspector => ({
  selectedItemId: null,
  inspectorTab: 'style',
  dataConfigOpen: false,
});

const cloneDocument = (document: ScreenEditDocument): ScreenEditDocument => {
  const filters = JSON.parse(
    JSON.stringify(document.filters ?? []),
  ) as UnifiedFilterDefinition[];
  const viewSets = JSON.parse(JSON.stringify(document.viewSets)) as ScreenViewSets;
  viewSets.filters = filters;
  return { filters, viewSets };
};

const sameDocument = (left: ScreenEditDocument, right: ScreenEditDocument) =>
  JSON.stringify(cloneDocument(left)) === JSON.stringify(cloneDocument(right));

const itemExists = (document: ScreenEditDocument, itemId: string | null) =>
  Boolean(itemId && document.viewSets.items.some((item) => item.id === itemId));

const inspectorAfterStep = (
  itemId: string | null,
  restored: ScreenEditDocument,
  current: ScreenEditInspector,
): ScreenEditInspector => {
  if (itemId) {
    if (!itemExists(restored, itemId)) {
      return emptyInspector();
    }
    if (current.selectedItemId === itemId) return current;
    return {
      selectedItemId: itemId,
      inspectorTab: 'style',
      dataConfigOpen: false,
    };
  }
  if (current.selectedItemId && !itemExists(restored, current.selectedItemId)) {
    return emptyInspector();
  }
  return current;
};

const present = (
  store: HistoryStore,
  document: ScreenEditDocument,
  inspector: ScreenEditInspector,
): ScreenEditSession => {
  const session: ScreenEditSession = {
    document,
    inspector,
    canUndo: store.past.length > 0,
    canRedo: store.future.length > 0,
  };
  stores.set(session, store);
  return session;
};

const readStore = (session: ScreenEditSession): HistoryStore => {
  const store = stores.get(session);
  if (!store) {
    throw new Error('Screen edit session is missing its history');
  }
  return {
    past: store.past,
    future: store.future,
    openField: store.openField,
  };
};

export const createScreenEditSession = (
  document: ScreenEditDocument,
  inspector?: Partial<ScreenEditInspector>,
): ScreenEditSession =>
  present(
    { past: [], future: [], openField: null },
    cloneDocument(document),
    { ...emptyInspector(), ...inspector },
  );

export const syncScreenEditInspector = (
  session: ScreenEditSession,
  inspector: ScreenEditInspector,
): ScreenEditSession =>
  present(readStore(session), session.document, inspector);

export const screenInspectorAfterReplace = (
  inspector: ScreenEditInspector,
  document: ScreenEditDocument,
): ScreenEditInspector => inspectorAfterStep(null, document, inspector);

export const closeScreenFieldEdit = (session: ScreenEditSession): ScreenEditSession => {
  const store = readStore(session);
  if (!store.openField) return session;
  return present(
    { ...store, openField: null },
    session.document,
    session.inspector,
  );
};

export const commitScreenEdit = (
  session: ScreenEditSession,
  commit: ScreenEditCommit,
): ScreenEditSession => {
  const nextDocument = cloneDocument(commit.document);
  if (sameDocument(session.document, nextDocument)) return session;

  const store = readStore(session);
  const itemId = commit.itemId ?? null;
  const fieldKey = commit.fieldKey ?? null;
  const sameOpenField = Boolean(
    fieldKey
    && store.openField
    && store.openField.fieldKey === fieldKey
    && store.openField.itemId === itemId
    && store.past.length > 0,
  );

  if (sameOpenField) {
    const past = store.past.slice();
    const tip = past[past.length - 1];
    past[past.length - 1] = { ...tip, after: nextDocument };
    return present(
      { past, future: [], openField: store.openField },
      nextDocument,
      session.inspector,
    );
  }

  const past = [
    ...store.past,
    {
      before: session.document,
      after: nextDocument,
      itemId,
      fieldKey,
    },
  ];
  const trimmed = past.length > SCREEN_EDIT_HISTORY_LIMIT
    ? past.slice(past.length - SCREEN_EDIT_HISTORY_LIMIT)
    : past;
  return present(
    {
      past: trimmed,
      future: [],
      openField: fieldKey ? { itemId, fieldKey } : null,
    },
    nextDocument,
    session.inspector,
  );
};

const moveHistory = (
  session: ScreenEditSession,
  direction: 'undo' | 'redo',
): ScreenEditSession => {
  const store = readStore(session);
  if (direction === 'undo') {
    const entry = store.past[store.past.length - 1];
    if (!entry) return session;
    const past = store.past.slice(0, -1);
    return present(
      { past, future: [...store.future, entry], openField: null },
      entry.before,
      inspectorAfterStep(entry.itemId, entry.before, session.inspector),
    );
  }
  const entry = store.future[store.future.length - 1];
  if (!entry) return session;
  const future = store.future.slice(0, -1);
  return present(
    { past: [...store.past, entry], future, openField: null },
    entry.after,
    inspectorAfterStep(entry.itemId, entry.after, session.inspector),
  );
};

export const undoScreenEdit = (session: ScreenEditSession) =>
  moveHistory(session, 'undo');

export const redoScreenEdit = (session: ScreenEditSession) =>
  moveHistory(session, 'redo');

export const screenViewSetsAfterResizeStop = (
  viewSets: ScreenViewSets,
  itemId: string,
  size: { w: number; h: number },
  position: { x: number; y: number },
): ScreenViewSets =>
  moveScreenItem(resizeScreenItem(viewSets, itemId, size), itemId, position);

const sameValue = (left: unknown, right: unknown) =>
  JSON.stringify(left ?? null) === JSON.stringify(right ?? null);

const singleContinuousKey = (
  before: Record<string, unknown> | undefined,
  after: Record<string, unknown> | undefined,
  keys: string[],
  prefix: string,
) => {
  const changed = keys.filter((key) => !sameValue(before?.[key], after?.[key]));
  if (changed.length !== 1) return null;
  return `${prefix}.${changed[0]}`;
};

export type ScreenGeometryField = 'x' | 'y' | 'w' | 'h';

const isGeometryField = (key: string): key is ScreenGeometryField =>
  key === 'x' || key === 'y' || key === 'w' || key === 'h';

export const screenItemFieldKey = (
  before: ScreenItem,
  after: ScreenItem,
  editedKey?: ScreenGeometryField,
): string | null => {
  if (before.id !== after.id) return null;
  const keys = ['content', 'x', 'y', 'w', 'h', 'textStyle', 'shapeStyle'] as const;
  const changed = keys.filter((key) => !sameValue(
    (before as unknown as Record<string, unknown>)[key],
    (after as unknown as Record<string, unknown>)[key],
  ));
  if (
    editedKey
    && changed.includes(editedKey)
    && changed.every(isGeometryField)
  ) {
    return editedKey;
  }
  if (changed.length !== 1) return null;
  const key = changed[0];
  if (key === 'content' || key === 'x' || key === 'y' || key === 'w' || key === 'h') {
    return key;
  }
  if (key === 'textStyle' && (isScreenTextItem(before) || isScreenTitleFrameItem(before))) {
    const previous = (before as ScreenTextItem).textStyle;
    const next = (after as ScreenTextItem).textStyle;
    return singleContinuousKey(
      previous as Record<string, unknown> | undefined,
      next as Record<string, unknown> | undefined,
      ['fontSize', 'color'],
      'textStyle',
    );
  }
  if (key === 'shapeStyle' && isScreenShapeItem(before) && isScreenShapeItem(after)) {
    return singleContinuousKey(
      before.shapeStyle as unknown as Record<string, unknown>,
      after.shapeStyle as unknown as Record<string, unknown>,
      ['backgroundColor', 'borderColor', 'borderWidth', 'shadow', 'gradientStart', 'gradientEnd'],
      'shapeStyle',
    );
  }
  return null;
};

export const screenViewportFieldKey = (
  before: ScreenViewportConfig,
  after: ScreenViewportConfig,
): string | null => {
  const changed = (['width', 'height', 'background'] as const).filter(
    (key) => !sameValue(before[key], after[key]),
  );
  if (changed.length !== 1) return null;
  if (changed[0] === 'width' || changed[0] === 'height') return `viewport.${changed[0]}`;
  if (
    before.background?.type === 'color'
    && after.background?.type === 'color'
    && before.background.color !== after.background.color
  ) {
    return 'viewport.background.color';
  }
  return null;
};

export type ScreenHistoryAction = 'undo' | 'redo';

const applyHistoryAction = (
  session: ScreenEditSession,
  action: ScreenHistoryAction,
): ScreenEditSession =>
  (action === 'undo' ? undoScreenEdit(session) : redoScreenEdit(session));

export const requestScreenHistory = (
  session: ScreenEditSession,
  action: ScreenHistoryAction,
  dataFormDirty: boolean,
):
  | { needsConfirm: true; session: ScreenEditSession }
  | { needsConfirm: false; applied: boolean; session: ScreenEditSession } => {
  const actionable = action === 'undo' ? session.canUndo : session.canRedo;
  if (!actionable) return { needsConfirm: false, applied: false, session };
  if (dataFormDirty) return { needsConfirm: true, session };
  return {
    needsConfirm: false,
    applied: true,
    session: applyHistoryAction(session, action),
  };
};

export const confirmScreenHistory = applyHistoryAction;

export const screenHistoryShortcut = (
  event: {
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    shiftKey: boolean;
    target: EventTarget | null;
  },
  enabled: boolean,
): ScreenHistoryAction | null => {
  if (!enabled || !event.ctrlKey || event.metaKey || event.shiftKey) return null;
  if (shortcutBlocked(event.target)) return null;
  const key = event.key.toLowerCase();
  if (key === 'z') return 'undo';
  if (key === 'y') return 'redo';
  return null;
};
