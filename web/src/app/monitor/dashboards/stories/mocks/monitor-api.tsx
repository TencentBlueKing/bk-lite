/**
 * Storybook 预览替身：替换 @/app/monitor/api（default export useMonitorApi）。
 * 仪表盘 core 只用到 getInstanceList，其余方法返回空壳以满足类型/调用。
 */
import { buildSyntheticInstanceList } from './synthetic-metrics';

const useMonitorApi = () => {
  const getInstanceList = async () => buildSyntheticInstanceList();

  const emptyList = async () => ({ count: 0, results: [] });
  const emptyData = async () => ({ data: [] });

  return {
    getInstanceList,
    getMonitorMetrics: emptyData,
    getMetricsGroup: emptyData,
    getMonitorObject: emptyList,
    getMonitorAlert: emptyList,
    getMonitorPlugin: emptyList,
    patchMonitorAlert: emptyData,
    getAllUsers: emptyData,
    getUnitList: emptyData
  };
};

export default useMonitorApi;
