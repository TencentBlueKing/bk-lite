export interface ScreenDataConfigCompareProps {
  item: unknown;
  onConfirm?: unknown;
  onClose?: unknown;
  onDirtyChange?: unknown;
  filterDefinitions?: unknown;
  unifiedFilterValues?: unknown;
  builtinNamespaceId?: unknown;
  configSection?: unknown;
  onConfigSectionChange?: unknown;
  screenFrame?: unknown;
  previewSingleStyle?: unknown;
  previewHost?: unknown;
  dataSourceManager: {
    dataSources: unknown;
    dataSourcesLoading: unknown;
    selectedDataSource?: unknown;
  };
}

export const areScreenDataConfigPropsEqual = (
  prev: ScreenDataConfigCompareProps,
  next: ScreenDataConfigCompareProps,
) =>
  prev.item === next.item &&
  prev.onConfirm === next.onConfirm &&
  prev.onClose === next.onClose &&
  prev.onDirtyChange === next.onDirtyChange &&
  prev.filterDefinitions === next.filterDefinitions &&
  prev.unifiedFilterValues === next.unifiedFilterValues &&
  prev.builtinNamespaceId === next.builtinNamespaceId &&
  prev.configSection === next.configSection &&
  prev.onConfigSectionChange === next.onConfigSectionChange &&
  prev.screenFrame === next.screenFrame &&
  prev.previewSingleStyle === next.previewSingleStyle &&
  prev.previewHost === next.previewHost &&
  prev.dataSourceManager.selectedDataSource ===
    next.dataSourceManager.selectedDataSource &&
  prev.dataSourceManager.dataSources === next.dataSourceManager.dataSources &&
  prev.dataSourceManager.dataSourcesLoading ===
    next.dataSourceManager.dataSourcesLoading;

/** 样式页藏起预览宿主；切回数据或交互再显示。预览开关状态留在表单里。 */
export const isScreenPreviewHostVisible = (
  inspectorTab: "style" | "data" | "interaction",
) => inspectorTab !== "style";

/**
 * 预览盖在画布右缘，不进 flex 流，画布列宽、缩放和居中保持不变。
 * 宿主本身不接指针，预览面板再打开指针。
 */
export const screenPreviewHostClassName = (visible: boolean) =>
  visible
    ? "pointer-events-none absolute inset-y-0 right-0 z-30 flex h-full max-w-full"
    : "hidden";
