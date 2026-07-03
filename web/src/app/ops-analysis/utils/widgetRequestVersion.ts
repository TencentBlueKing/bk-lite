interface WidgetRequestVersionOptions {
  reloadVersion: string;
  filterSearchVersion: number;
  namespaceSearchVersion: number;
  hasEnabledFilterBindings: boolean;
  widgetUsesNamespace: boolean;
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
