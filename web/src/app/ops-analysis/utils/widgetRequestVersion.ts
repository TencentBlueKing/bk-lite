interface WidgetRequestVersionOptions {
  reloadVersion: string;
  filterSearchVersion: number;
  namespaceSearchVersion: number;
  hasEnabledFilterBindings: boolean;
  widgetUsesNamespace: boolean;
}

interface WidgetInitialDataWaitOptions {
  isSceneWidget: boolean;
  isTableLikeChart: boolean;
  hasDataSourceId: boolean;
  hasResolvedDataSource: boolean;
  hasRawPayload: boolean;
  hasDataValidation: boolean;
  requestEnabled: boolean;
  hasRequested: boolean;
}

export const buildWidgetRequestVersionKey = ({
  reloadVersion,
  filterSearchVersion,
  namespaceSearchVersion,
  hasEnabledFilterBindings,
  widgetUsesNamespace,
}: WidgetRequestVersionOptions) =>
  [
    reloadVersion,
    hasEnabledFilterBindings ? filterSearchVersion : 0,
    widgetUsesNamespace ? namespaceSearchVersion : 0,
  ].join(':');

export const shouldWaitForInitialWidgetData = ({
  isSceneWidget,
  isTableLikeChart,
  hasDataSourceId,
  hasResolvedDataSource,
  hasRawPayload,
  hasDataValidation,
  requestEnabled,
  hasRequested,
}: WidgetInitialDataWaitOptions) => {
  if (
    isSceneWidget ||
    isTableLikeChart ||
    !hasDataSourceId ||
    hasRawPayload ||
    hasDataValidation
  ) {
    return false;
  }

  return !hasResolvedDataSource || (requestEnabled && !hasRequested);
};
