import useApiClient from '@/utils/request';
import { AxiosRequestConfig } from 'axios';
import { SearchParams } from '@/app/monitor/types/search';
import { ViewInstanceSearchProps } from '@/app/monitor/types/view';
import { InstanceParam } from '@/app/monitor/types';

const useViewApi = () => {
  const { get, post } = useApiClient();

  const getInstanceQuery = async (
    params: SearchParams = {
      query: '',
    }
  ) => {
    return await get(`/monitor/api/metrics_instance/query_range/`, {
      params,
    });
  };

  const getInstanceSearch = async (
    objectId: React.Key,
    data: InstanceParam,
    config?: AxiosRequestConfig
  ) => {
    return await post(
      `/monitor/api/monitor_instance/${objectId}/search/`,
      data,
      config
    );
  };

  const getInstanceQueryParams = async (
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
  };

  const getMetricsInstanceQuery = async (params: ViewInstanceSearchProps) => {
    return await get(`/monitor/api/metrics_instance/query_by_instance/`, {
      params,
    });
  };

  return {
    getInstanceQuery,
    getInstanceSearch,
    getInstanceQueryParams,
    getMetricsInstanceQuery,
  };
};

export default useViewApi;
