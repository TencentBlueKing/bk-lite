import useApiClient from '@/utils/request';
import React from 'react';
import { InstanceParam } from '@/app/monitor/types';

interface MetricsParam {
  monitor_object_id?: React.Key;
  monitor_plugin_id?: string | number;
  monitor_object_name?: string;
  name?: string;
}

const useMonitorApi = () => {
  const { get, patch } = useApiClient();

  const getMonitorMetrics = async (params: MetricsParam = {}) => {
    return await get(`/monitor/api/metrics/`, {
      params,
    });
  };

  const getMetricsGroup = async (params: MetricsParam = {}) => {
    return await get(`/monitor/api/metrics_group/`, {
      params,
    });
  };

  const getMonitorObject = async (
    params: {
      name?: string;
      add_instance_count?: boolean;
      add_policy_count?: boolean;
    } = {}
  ) => {
    return await get('/monitor/api/monitor_object/', {
      params,
    });
  };

  const getMonitorAlert = async (
    params: {
      status_in?: string[];
      level_in?: string;
      monitor_instance_id?: string;
      monitor_objects?: React.Key;
      content?: string;
      page?: number;
      page_size?: number;
      created_at_after?: string;
      created_at_before?: string;
    } = {}
  ) => {
    return await get(`/monitor/api/monitor_alert/`, {
      params,
    });
  };

  const getInstanceList = async (
    objectId?: React.Key,
    params: InstanceParam = {}
  ) => {
    return await get(`/monitor/api/monitor_instance/${objectId}/list/`, {
      params,
    });
  };

  const getMonitorPlugin = async (
    params: {
      monitor_object_id?: React.Key | null;
      name?: string;
    } = {}
  ) => {
    return await get('/monitor/api/monitor_plugin/', {
      params,
    });
  };

  const patchMonitorAlert = async (
    id: React.Key,
    data: {
      status?: string;
    }
  ) => {
    return await patch(`/monitor/api/monitor_alert/${id}/`, data);
  };

  return {
    getMonitorMetrics,
    getMetricsGroup,
    getMonitorObject,
    getMonitorAlert,
    getInstanceList,
    getMonitorPlugin,
    patchMonitorAlert,
  };
};

export default useMonitorApi;
