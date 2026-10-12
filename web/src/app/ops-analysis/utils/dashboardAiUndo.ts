import type {
  DashboardLayoutItem,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';

export const DASHBOARD_UNDO_LIMIT = 30;

export interface DashboardUndoEntry {
  layout: DashboardLayoutItem[];
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedDefinitions: UnifiedFilterDefinition[];
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
}

const cloneJson = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export const cloneDashboardUndoEntry = (entry: DashboardUndoEntry): DashboardUndoEntry => cloneJson(entry);

export const pushDashboardUndo = (
  stack: DashboardUndoEntry[],
  entry: DashboardUndoEntry,
  limit = DASHBOARD_UNDO_LIMIT,
): DashboardUndoEntry[] => {
  const snapshot = cloneDashboardUndoEntry(entry);
  const next = [...stack, snapshot];
  return next.length > limit ? next.slice(next.length - limit) : next;
};

export const popDashboardUndo = (
  stack: DashboardUndoEntry[],
): { stack: DashboardUndoEntry[]; entry: DashboardUndoEntry | null } => {
  if (!stack.length) return { stack, entry: null };
  return {
    stack: stack.slice(0, -1),
    entry: stack[stack.length - 1],
  };
};

export const recordDashboardEdit = (
  undo: DashboardUndoEntry[],
  entry: DashboardUndoEntry,
) => ({
  undo: pushDashboardUndo(undo, entry),
  redo: [] as DashboardUndoEntry[],
});

export const undoDashboardEdit = (
  undo: DashboardUndoEntry[],
  redo: DashboardUndoEntry[],
  current: DashboardUndoEntry,
) => {
  const popped = popDashboardUndo(undo);
  if (!popped.entry) return { undo, redo, entry: null };
  return {
    undo: popped.stack,
    redo: pushDashboardUndo(redo, current),
    entry: popped.entry,
  };
};

export const redoDashboardEdit = (
  undo: DashboardUndoEntry[],
  redo: DashboardUndoEntry[],
  current: DashboardUndoEntry,
) => {
  const popped = popDashboardUndo(redo);
  if (!popped.entry) return { undo, redo, entry: null };
  return {
    undo: pushDashboardUndo(undo, current),
    redo: popped.stack,
    entry: popped.entry,
  };
};
