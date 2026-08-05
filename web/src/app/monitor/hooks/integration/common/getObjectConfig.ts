import { useCallback } from 'react';
import { useMonitorConfig } from '../index';
import { normalizeDashboardDisplay } from '../configContracts';

export const useObjectConfigInfo = (objectName?: string | null) => {
  const { resolveConfig, ready } = useMonitorConfig(objectName);

  const getCollectType = useCallback(
    (name: string, pluginName: string) => {
      const objectConfig = resolveConfig(name);
      return objectConfig?.collectTypes?.[pluginName];
    },
    [resolveConfig]
  );

  const getInstanceType = useCallback(
    (name: string) => {
      const objectConfig = resolveConfig(name);
      return objectConfig?.instance_type || '--';
    },
    [resolveConfig]
  );

  const getGroupIds = useCallback(
    (name: string) => {
      const objectConfig = resolveConfig(name);
      return objectConfig?.groupIds;
    },
    [resolveConfig]
  );

  const getDashboardDisplay = useCallback(
    (name: string) => {
      const objectConfig = resolveConfig(name);
      return normalizeDashboardDisplay(objectConfig?.dashboardDisplay);
    },
    [resolveConfig]
  );

  return {
    ready,
    getCollectType,
    getInstanceType,
    getGroupIds,
    getDashboardDisplay
  };
};
