import useApiClient from '@/utils/request';
import React from 'react';
import { LogAlertParams, StrategyFields } from '@/app/log/types/event';

const useLogEventApi = () => {
  const { get, post, del, put, patch } = useApiClient();

  const getSystemChannelList = async () => {
    return await get('/log/system_mgmt/search_channel_list/');
  };

  const getPolicy = async (
    id?: React.Key,
    params: {
      name?: string;
      page?: number;
      page_size?: number;
      collect_type?: React.Key;
    } = {}
  ) => {
    return await get(`/log/policy/${id}`, {
      params,
    });
  };

  const createPolicy = async (data: StrategyFields) => {
    return await post('/log/policy/', data);
  };

  const patchPolicy = async (data: StrategyFields) => {
    const { id, ...rest } = data;
    return await patch(`/log/policy/${id}/`, rest);
  };

  const updatePolicy = async (data: StrategyFields) => {
    const { id, ...rest } = data;
    return await put(`/log/policy/${id}/`, rest);
  };

  const deletePolicy = async (id: React.Key) => {
    return await del(`/log/policy/${id}/`);
  };

  const getLogAlert = async (params: LogAlertParams = {}) => {
    return await get(`/log/alert/`, {
      params,
    });
  };

  const patchLogAlert = async (data: LogAlertParams) => {
    const { id, ...rest } = data;
    return await patch(`/log/alert/${id}/`, rest);
  };

  const geEventList = async (
    params: {
      alert_id?: React.Key;
      page?: number;
      page_size?: number;
    } = {}
  ) => {
    return await get(`/log/event/`, {
      params,
    });
  };

  const getEventRaw = async (id?: React.Key) => {
    return await get(`/log/alert/last_event/`, {
      params: {
        alert_id: id,
      },
    });
  };

  const getEventRawData = async (id?: React.Key) => {
    return await get(`/log/event_raw_data/by_event_id/`, {
      params: {
        event_id: id,
      },
    });
  };

  const getLogAlertStats = async (params: LogAlertParams = {}) => {
    return await get(`/log/alert/stats/`, {
      params,
    });
  };

  return {
    createPolicy,
    getPolicy,
    getSystemChannelList,
    patchPolicy,
    updatePolicy,
    deletePolicy,
    getLogAlert,
    getLogAlertStats,
    patchLogAlert,
    geEventList,
    getEventRaw,
    getEventRawData,
  };
};

export default useLogEventApi;
