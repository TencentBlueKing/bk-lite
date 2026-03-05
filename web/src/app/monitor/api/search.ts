import useApiClient from '@/utils/request';
import React from 'react';
import type {
  SaveConditionParams,
  ListConditionParams
} from '@/app/monitor/types/search';

const useSearchApi = () => {
  const { get, post, del } = useApiClient();

  const getMonitorConditions = async (params: ListConditionParams = {}) => {
    return await get('/monitor/api/monitor_condition/', { params });
  };

  const saveMonitorCondition = async (data: SaveConditionParams) => {
    return await post('/monitor/api/monitor_condition/', data);
  };

  const deleteMonitorCondition = async (id: React.Key) => {
    return await del(`/monitor/api/monitor_condition/${id}/`);
  };

  return {
    getMonitorConditions,
    saveMonitorCondition,
    deleteMonitorCondition
  };
};

export default useSearchApi;
