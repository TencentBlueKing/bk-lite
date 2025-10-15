import useApiClient from '@/utils/request';
import { SearchParams } from '@/app/monitor/types/search';
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
    data: InstanceParam
  ) => {
    return await post(
      `/monitor/api/monitor_instance/${objectId}/search/`,
      data
    );
  };

  const getInstanceQueryParams = async (
    name: string,
    params: {
      monitor_object_id?: React.Key;
    } = {}
  ) => {
    return await get(
      `/monitor/api/monitor_instance/query_params_enum/${name}/`,
      {
        params,
      }
    );
  };

  return {
    getInstanceQuery,
    getInstanceSearch,
    getInstanceQueryParams,
  };
};

export default useViewApi;
