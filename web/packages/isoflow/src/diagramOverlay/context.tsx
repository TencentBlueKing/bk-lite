import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState
} from 'react';
import type {
  EditorModeEnum,
  ItemControls,
  IconPickerRequest,
  ItemControlsExtraTarget,
  NodeBindingMark,
  NodeMetrics,
  NodeStatus,
  RectangleStatus
} from 'src/types';
import { useUiStateStore } from 'src/stores/uiStateStore';
import {
  DiagramCallbacksRef,
  emitItemSelect,
  isSelectableDiagramItem
} from './callbacks';

export interface DiagramVisual {
  nodeStatus?: Record<string, NodeStatus>;
  nodeMetrics?: Record<string, NodeMetrics>;
  nodeBinding?: Record<string, NodeBindingMark>;
  rectangleStatus?: Record<string, RectangleStatus>;
  highlightedItemId?: string;
  editorMode: keyof typeof EditorModeEnum;
  hoveredRectangleId: string | null;
  setHoveredRectangleId: (id: string | null) => void;
}

const EMPTY_VISUAL: DiagramVisual = {
  editorMode: 'EDITABLE',
  hoveredRectangleId: null,
  setHoveredRectangleId: () => undefined
};

const DiagramVisualContext = createContext<DiagramVisual>(EMPTY_VISUAL);

const DiagramCallbacksContext = createContext<DiagramCallbacksRef>({
  current: {
    editorMode: 'EDITABLE',
    lastSelectKey: ''
  }
});

interface ProviderProps {
  children: React.ReactNode;
  onItemClick?: DiagramCallbacksRef['current']['onItemClick'];
  onItemSelect?: DiagramCallbacksRef['current']['onItemSelect'];
  nodeStatus?: Record<string, NodeStatus>;
  nodeMetrics?: Record<string, NodeMetrics>;
  nodeBinding?: Record<string, NodeBindingMark>;
  rectangleStatus?: Record<string, RectangleStatus>;
  highlightedItemId?: string;
  editorMode?: keyof typeof EditorModeEnum;
}

export const DiagramOverlayProvider = ({
  children,
  onItemClick,
  onItemSelect,
  nodeStatus,
  nodeMetrics,
  nodeBinding,
  rectangleStatus,
  highlightedItemId,
  editorMode = 'EDITABLE'
}: ProviderProps) => {
  const [hoveredRectangleId, setHoveredRectangleId] = useState<string | null>(null);
  const setHovered = useCallback((id: string | null) => {
    setHoveredRectangleId(id);
  }, []);
  const callbacksRef = useRef<DiagramCallbacksRef['current']>({
    editorMode,
    lastSelectKey: ''
  });
  const pendingEditSelectClearRef = useRef<(() => void) | null>(null);

  if (
    callbacksRef.current.editorMode === 'EDITABLE' &&
    editorMode !== 'EDITABLE' &&
    callbacksRef.current.lastSelectKey !== '' &&
    callbacksRef.current.onItemSelect
  ) {
    const notify = callbacksRef.current.onItemSelect;
    pendingEditSelectClearRef.current = () => {
      notify(null);
    };
  }

  if (callbacksRef.current.editorMode !== editorMode) {
    callbacksRef.current.lastSelectKey = '';
  }

  callbacksRef.current.onItemClick = onItemClick;
  callbacksRef.current.onItemSelect = onItemSelect;
  callbacksRef.current.editorMode = editorMode;

  useLayoutEffect(() => {
    const notify = pendingEditSelectClearRef.current;
    pendingEditSelectClearRef.current = null;
    if (notify) notify();
  });

  const visual = useMemo<DiagramVisual>(() => {
    return {
      nodeStatus,
      nodeMetrics,
      nodeBinding,
      rectangleStatus,
      highlightedItemId,
      editorMode,
      hoveredRectangleId,
      setHoveredRectangleId: setHovered
    };
  }, [
    editorMode,
    highlightedItemId,
    hoveredRectangleId,
    nodeBinding,
    nodeMetrics,
    nodeStatus,
    rectangleStatus,
    setHovered
  ]);

  return (
    <DiagramCallbacksContext.Provider value={callbacksRef}>
      <DiagramVisualContext.Provider value={visual}>
        <SelectionDismissWatcher
          callbacksRef={callbacksRef}
          editorMode={editorMode}
        />
        {children}
      </DiagramVisualContext.Provider>
    </DiagramCallbacksContext.Provider>
  );
};

const SelectionDismissWatcher = ({
  callbacksRef,
  editorMode
}: {
  callbacksRef: DiagramCallbacksRef;
  editorMode: keyof typeof EditorModeEnum;
}) => {
  const itemControls = useUiStateStore((state) => {
    return state.itemControls;
  });
  const prevControls = useRef<ItemControls | null | undefined>(undefined);

  useEffect(() => {
    const prev = prevControls.current;
    prevControls.current = itemControls;

    if (prev === undefined || editorMode !== 'EDITABLE') return;

    if (
      isSelectableDiagramItem(prev) &&
      !isSelectableDiagramItem(itemControls)
    ) {
      emitItemSelect(callbacksRef, null);
    }
  }, [callbacksRef, editorMode, itemControls]);

  return null;
};

export const useDiagramVisual = () => {
  return useContext(DiagramVisualContext);
};

export const useDiagramCallbacksRef = () => {
  return useContext(DiagramCallbacksContext);
};

type RenderItemControlsExtra = (item: ItemControlsExtraTarget) => React.ReactNode;

/** Host-owned icon picker. The scene asks it to open; it does not draw a dialog. */
export const IconPickerContext = createContext<
  ((request: IconPickerRequest) => void) | undefined
>(undefined);

export const useIconPicker = () => {
  return useContext(IconPickerContext);
};

/** Host content for the item settings panels. Kept apart from the visual context so a new render function does not repaint the scene. */
export const ItemControlsExtraContext = createContext<RenderItemControlsExtra | undefined>(undefined);

export const useItemControlsExtra = (item: ItemControlsExtraTarget) => {
  const render = useContext(ItemControlsExtraContext);

  return render ? render(item) : null;
};
