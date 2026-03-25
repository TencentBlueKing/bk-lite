import {
  SearchParams,
  StoreConditions,
  FieldTopStatsParams,
  FieldTopStatsResponse
} from '@/app/log/types/search';
import useApiClient from '@/utils/request';
import React from 'react';

const useSearchApi = () => {
  const { post, get, del } = useApiClient();

  const getLogs = async (data: SearchParams) => {
    return await post(`/log/search/search/`, data);
  };

  const getHits = async (data: SearchParams) => {
    return await post(`/log/search/hits/`, data);
  };

  const getLogTail = async (params = {}) => {
    return await get(`/log/search/tail/`, { params });
  };

  const getFieldTopStats = async (
    data: FieldTopStatsParams
  ): Promise<FieldTopStatsResponse> => {
    return await post(`/log/search/top_stats/`, data);
  };

  const saveLogCondition = async (data: StoreConditions) => {
    return await post(`/log/search_conditions/`, data);
  };

  const getLogCondition = async (params = {}) => {
    return await get(`/log/search_conditions/`, { params });
  };

  const delLogCondition = async (id: React.Key) => {
    return await del(`/log/search_conditions/${id}/`);
  };

  return {
    getLogs,
    getHits,
    getLogTail,
    getFieldTopStats,
    saveLogCondition,
    getLogCondition,
    delLogCondition
  };
};

export default useSearchApi;
