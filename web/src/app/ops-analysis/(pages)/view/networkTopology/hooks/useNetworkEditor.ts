import { useCallback, useMemo, useState } from 'react';

/**
 * 网络拓扑编辑模式 + 选中状态 + dirty 标记 hook。
 *
 * 设计(design.md §7.1):
 * - editMode:切换只读 / 编辑
 * - 选中节点 / 选中连线用于打开 Drawer
 * - dirty = editMode && 当前未保存修改(vs 上一份 savedSnapshot)
 *
 * 不耦合 X6 graph instance,这样可以在画布未初始化前就使用。
 */

export interface UseNetworkEditorParams {
  /** 当前 view_sets(可编辑状态)。 */
  config: unknown;
  /** 已落库的 view_sets(用于 diff)。 */
  savedConfig: unknown;
}

export interface UseNetworkEditorReturn {
  editMode: boolean;
  selectedNodeId: string | null;
  selectedLinkId: string | null;
  isDirty: boolean;
  enterEditMode: () => void;
  exitEditMode: (revertConfig: () => void) => void;
  toggleEditMode: (revertConfig: () => void) => void;
  setSelectedNodeId: (id: string | null) => void;
  setSelectedLinkId: (id: string | null) => void;
  markSaved: (nextConfig: unknown) => void;
  /** 初始化/切换画布时重置编辑状态并标记当前 config。 */
  resetConfig: (next: unknown) => void;
}

const stableStringify = (value: unknown): string => {
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
};

export const useNetworkEditor = ({
  config,
  savedConfig,
}: UseNetworkEditorParams): UseNetworkEditorReturn => {
  const [editMode, setEditMode] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedLinkId, setSelectedLinkId] = useState<string | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState(() =>
    stableStringify(savedConfig),
  );

  const isDirty = useMemo(() => {
    if (!editMode) return false;
    return stableStringify(config) !== savedSnapshot;
  }, [config, editMode, savedSnapshot]);

  const enterEditMode = useCallback(() => {
    setEditMode(true);
    setSavedSnapshot(stableStringify(config));
  }, [config]);

  const exitEditMode = useCallback((revertConfig: () => void) => {
    revertConfig();
    setEditMode(false);
    setSelectedNodeId(null);
    setSelectedLinkId(null);
  }, []);

  const toggleEditMode = useCallback(
    (revertConfig: () => void) => {
      if (editMode) {
        exitEditMode(revertConfig);
      } else {
        enterEditMode();
      }
    },
    [editMode, enterEditMode, exitEditMode],
  );

  const markSaved = useCallback(
    (nextConfig: unknown) => {
      setSavedSnapshot(stableStringify(nextConfig));
    },
    [],
  );

  const resetConfig = useCallback((next: unknown) => {
    setSavedSnapshot(stableStringify(next));
    setEditMode(false);
    setSelectedNodeId(null);
    setSelectedLinkId(null);
  }, []);

  return {
    editMode,
    selectedNodeId,
    selectedLinkId,
    isDirty,
    enterEditMode,
    exitEditMode,
    toggleEditMode,
    setSelectedNodeId,
    setSelectedLinkId,
    markSaved,
    resetConfig,
  };
};
