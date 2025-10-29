import { useMonitorConfig } from '@/app/monitor/hooks/integration/index';

export const useObjectConfigInfo = () => {
  const configs = useMonitorConfig();
  const getCollectType = (objectName: string, pluginName: string) => {
    if (pluginName === 'K8S') return 'k8s';
    return (
      configs.config[objectName]?.plugins?.[pluginName]?.getPluginCfg({
        mode: 'auto',
      })?.collect_type || '--'
    );
  };
  const getGroupIds = (objectName: string) => {
    return configs.config[objectName]?.groupIds;
  };
  const getInstanceType = (objectName: string) => {
    return configs.config[objectName]?.instance_type || '';
  };
  const getTableDiaplay = (objectName: string) => {
    return configs.config[objectName]?.tableDiaplay || [];
  };
  const getDashboardDisplay = (objectName: string) => {
    return configs.config[objectName]?.dashboardDisplay || [];
  };
  return {
    getCollectType,
    getGroupIds,
    getInstanceType,
    getTableDiaplay,
    getDashboardDisplay,
  };
};
