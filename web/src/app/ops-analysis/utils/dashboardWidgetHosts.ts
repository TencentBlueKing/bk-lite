export interface DashboardWidgetHostRegistry<T> {
  dashboardScopeKey: string | null;
  hosts: Map<string, T>;
}

export const createDashboardWidgetHostRegistry = <T>(): DashboardWidgetHostRegistry<T> => ({
  dashboardScopeKey: null,
  hosts: new Map<string, T>(),
});

export const prepareDashboardWidgetHosts = <T>(
  registry: DashboardWidgetHostRegistry<T>,
  dashboardScopeKey: string,
  widgetIds: Iterable<string>,
): boolean => {
  const preserveExistingHosts = registry.dashboardScopeKey === dashboardScopeKey;
  const desiredWidgetIds = new Set(widgetIds);

  if (!preserveExistingHosts) {
    registry.hosts.clear();
  } else {
    Array.from(registry.hosts.keys()).forEach((widgetId) => {
      if (!desiredWidgetIds.has(widgetId)) {
        registry.hosts.delete(widgetId);
      }
    });
  }

  registry.dashboardScopeKey = dashboardScopeKey;
  return preserveExistingHosts;
};

export const getOrCreateDashboardWidgetHost = <T>(
  registry: DashboardWidgetHostRegistry<T>,
  widgetId: string,
  createHost: () => T,
): T => {
  const existingHost = registry.hosts.get(widgetId);
  if (existingHost !== undefined) {
    return existingHost;
  }

  const host = createHost();
  registry.hosts.set(widgetId, host);
  return host;
};
