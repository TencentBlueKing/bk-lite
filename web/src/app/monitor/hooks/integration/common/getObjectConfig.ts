import { useMonitorConfig } from '../index';

export const useObjectConfigInfo = () => {
  const { config } = useMonitorConfig();

  // 获取对象的 collect_type
  const getCollectType = (objectName: string, pluginName: string) => {
    const objectConfig = config[objectName];
    return objectConfig?.collectTypes?.[pluginName];
  };

  // 获取对象的 instance_type
  const getInstanceType = (objectName: string) => {
    const objectConfig = config[objectName];
    return objectConfig?.instance_type || '--';
  };

  // 获取对象的 groupIds
  const getGroupIds = (objectName: string) => {
    const objectConfig = config[objectName];
    return objectConfig?.groupIds;
  };

  // 获取对象的 tableDiaplay
  const getTableDiaplay = (objectName: string) => {
    const objectConfig = config[objectName];
    return objectConfig?.tableDiaplay;
  };

  // 获取对象的 dashboardDisplay
  const getDashboardDisplay = (objectName: string) => {
    const objectConfig = config[objectName];
    return objectConfig?.dashboardDisplay;
  };

  return {
    getCollectType,
    getInstanceType,
    getGroupIds,
    getTableDiaplay,
    getDashboardDisplay,
  };
};
