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
  dataSourceLookupLoading: boolean;
  hasRawPayload: boolean;
  hasDataValidation: boolean;
  requestEnabled: boolean;
  hasRequested: boolean;
}

export type DataSourceLookupStatus = 'idle' | 'loading' | 'success' | 'error';

type WidgetDataSourceState =
  | 'ready'
  | 'loading'
  | 'data-source-load-error'
  | 'data-source-not-found';

interface WidgetDataSourceStateOptions {
  hasDataSourceId: boolean;
  hasResolvedDataSource: boolean;
  lookupStatus: DataSourceLookupStatus;
}

export const resolveWidgetDataSourceState = ({
  hasDataSourceId,
  hasResolvedDataSource,
  lookupStatus,
}: WidgetDataSourceStateOptions): WidgetDataSourceState => {
  if (!hasDataSourceId || hasResolvedDataSource) {
    return 'ready';
  }

  if (lookupStatus === 'error') {
    return 'data-source-load-error';
  }

  if (lookupStatus === 'success') {
    return 'data-source-not-found';
  }

  return 'loading';
};

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
  hasDataSourceId,
  hasResolvedDataSource,
  dataSourceLookupLoading,
  hasRawPayload,
  hasDataValidation,
  requestEnabled,
  hasRequested,
}: WidgetInitialDataWaitOptions) => {
  if (
    isSceneWidget ||
    !hasDataSourceId ||
    hasRawPayload ||
    hasDataValidation
  ) {
    return false;
  }

  if (!hasResolvedDataSource) {
    return dataSourceLookupLoading;
  }

  return requestEnabled && !hasRequested;
};
