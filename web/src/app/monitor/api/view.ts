import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { AxiosRequestConfig } from 'axios';
import { SearchParams } from '@/app/monitor/types/search';
import {
  ViewColumnPreference,
  ViewInstanceSearchProps,
} from '@/app/monitor/types/view';
import { InstanceParam } from '@/app/monitor/types';

const useViewApi = () => {
  const { get, post, put } = useApiClient();

  // 这些函数会被消费方放进 useEffect/useCallback 依赖数组(如各对象盘的 TopN 取数 effect)。
  // 必须用 useCallback 固定引用,否则每次重渲染都生成新函数 → effect 反复触发 → 重复发起查询。
  const getInstanceQuery = useCallback(
    async (
      params: SearchParams = {
        query: '',
      }
    ) => {
      return await get(`/monitor/api/metrics_instance/query_range/`, {
        params,
      });
    },
    [get]
  );

  const getInstanceSearch = useCallback(
    async (
      objectId: React.Key,
      data: InstanceParam,
      config?: AxiosRequestConfig
    ) => {
      return await post(
        `/monitor/api/monitor_instance/${objectId}/search/`,
        data,
        config
      );
    },
    [post]
  );

  const getInstanceQueryParams = useCallback(
    async (
      name: string,
      params: {
        monitor_object_id?: React.Key;
      } = {},
      config?: AxiosRequestConfig
    ) => {
      return await get(
        `/monitor/api/monitor_instance/query_params_enum/${name}/`,
        {
          params,
          ...config,
        }
      );
    },
    [get]
  );

  const getMetricsInstanceQuery = useCallback(
    async (params: ViewInstanceSearchProps) => {
      return await get(`/monitor/api/metrics_instance/query_by_instance/`, {
        params,
      });
    },
    [get]
  );

  const getViewColumnPreference = useCallback(
    async (objectId: React.Key, config?: AxiosRequestConfig) => {
      return await get<ViewColumnPreference | null>(
        `/monitor/api/monitor_object/${objectId}/view_column_preference/`,
        config
      );
    },
    [get]
  );

  const saveViewColumnPreference = useCallback(
    async (objectId: React.Key, fieldKeys: string[]) => {
      return await put<ViewColumnPreference>(
        `/monitor/api/monitor_object/${objectId}/view_column_preference/`,
        { field_keys: fieldKeys }
      );
    },
    [put]
  );

  return {
    getInstanceQuery,
    getInstanceSearch,
    getInstanceQueryParams,
    getMetricsInstanceQuery,
    getViewColumnPreference,
    saveViewColumnPreference,
  };
};

export default useViewApi;
