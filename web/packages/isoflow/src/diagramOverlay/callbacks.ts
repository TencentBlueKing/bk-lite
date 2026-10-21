import type {
  DiagramItemHit,
  DiagramPointerEvent,
  EditorModeEnum
} from 'src/types';

export interface DiagramCallbacks {
  onItemClick?: (
    item: DiagramItemHit | null,
    event?: DiagramPointerEvent
  ) => void;
  onItemSelect?: (item: DiagramItemHit | null) => void;
  editorMode: keyof typeof EditorModeEnum;
  lastSelectKey: string;
}

export type DiagramCallbacksRef = {
  current: DiagramCallbacks;
};

export const isSelectableDiagramItem = (
  item: { type: string; id?: string } | null | undefined
): item is DiagramItemHit => {
  return (
    !!item &&
    typeof item.id === 'string' &&
    (item.type === 'ITEM' ||
      item.type === 'RECTANGLE' ||
      item.type === 'CONNECTOR')
  );
};

export const emitItemSelect = (
  ref: DiagramCallbacksRef,
  item: DiagramItemHit | null
) => {
  const current = ref.current;

  if (current.editorMode !== 'EDITABLE' || !current.onItemSelect) return;

  if (item === null && current.lastSelectKey === '') return;

  current.lastSelectKey = item ? `${item.type}:${item.id}` : '';
  current.onItemSelect(item);
};
