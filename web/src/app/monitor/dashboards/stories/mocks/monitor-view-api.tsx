/**
 * Storybook 预览替身：替换 @/app/monitor/api/view。
 * 不发任何网络请求，getInstanceQuery 返回按语义生成的合成时序数据。
 */
import { buildSyntheticQueryResult } from './synthetic-metrics';

const useViewApi = () => {
  const getInstanceQuery = async (params: { query?: string; source_unit?: string } = {}) =>
    buildSyntheticQueryResult(params);

  const getInstanceSearch = async () => ({ count: 0, results: [] });
  const getInstanceQueryParams = async () => ({ data: [] });
  const getMetricsInstanceQuery = async () => ({ data: { result: [] } });

  return {
    getInstanceQuery,
    getInstanceSearch,
    getInstanceQueryParams,
    getMetricsInstanceQuery
  };
};

export default useViewApi;
