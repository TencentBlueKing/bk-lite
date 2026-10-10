export interface ScreenDataConfigCompareProps {
  item: unknown;
  onConfirm?: unknown;
  onClose?: unknown;
  onDirtyChange?: unknown;
  filterDefinitions?: unknown;
  unifiedFilterValues?: unknown;
  builtinNamespaceId?: unknown;
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
  prev.dataSourceManager.selectedDataSource ===
    next.dataSourceManager.selectedDataSource &&
  prev.dataSourceManager.dataSources === next.dataSourceManager.dataSources &&
  prev.dataSourceManager.dataSourcesLoading ===
    next.dataSourceManager.dataSourcesLoading;
