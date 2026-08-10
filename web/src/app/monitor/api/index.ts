import useApiClient from '@/utils/request';
import React from 'react';
import { AxiosRequestConfig } from 'axios';
import {
  GroupInfo,
  InstanceParam,
  MetricItem,
  ObjectItem
} from '@/app/monitor/types';

export interface MetricsParam {
  monitor_object_id?: React.Key;
  monitor_plugin_id?: string | number;
  monitor_object_name?: string;
  id?: React.Key;
  id_in?: string;
  name?: string;
  name_in?: string;
  keyword?: string;
  include_ifmib?: boolean;
  is_ifmib?: boolean;
  page?: number;
  page_size?: number;
}

export interface MetricCatalogPage<T> {
  count: number;
  items: T[];
  metric_groups?: MetricCatalogGroup[];
}

export interface MetricCatalogGroup extends GroupInfo {
  id: number;
  monitor_plugin?: React.Key;
  display_name?: string;
  is_pre?: boolean;
}

const isMetricCatalogPage = <T,>(value: unknown): value is MetricCatalogPage<T> => (
  typeof value === 'object'
  && value !== null
  && 'count' in value
  && 'items' in value
  && Array.isArray(value.items)
);

const useMonitorApi = () => {
  const { get, patch } = useApiClient();

  const getMetricCatalogPage = async <T,>(
    url: string,
    params: MetricsParam,
    config?: AxiosRequestConfig
  ): Promise<MetricCatalogPage<T>> => {
    const response: unknown = await get(url, {
      ...config,
      params: {
        ...params,
        page: params.page ?? 1,
        page_size: params.page_size ?? 100
      }
    });
    if (!isMetricCatalogPage<T>(response)) {
      return { count: 0, items: [] };
    }
    return response;
  };

  const getMonitorMetrics = async (
    params: MetricsParam = {},
    config?: AxiosRequestConfig
  ) => {
    return getMetricCatalogPage<MetricItem>(
      `/monitor/api/metrics/`,
      params,
      config
    );
  };

  const getMetricsGroup = async (
    params: MetricsParam = {},
    config?: AxiosRequestConfig
  ) => {
    return getMetricCatalogPage<MetricCatalogGroup>(
      `/monitor/api/metrics_group/`,
      params,
      config
    );
  };

  const getMonitorObject = async (
    params: {
      name?: string;
      add_instance_count?: boolean;
      add_policy_count?: boolean;
      include_invisible?: boolean; // 是否包含不可见对象，默认 false
    } = {}
  ) => {
    const { include_invisible, ...queryParams } = params;
    const result = await get('/monitor/api/monitor_object/', {
      params: queryParams
    });
    // 默认过滤掉不可见对象（is_visible=false）
    if (!include_invisible && Array.isArray(result)) {
      return result.filter((item: ObjectItem) => item.is_visible !== false);
    }
    return result;
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
    } = {},
    config?: AxiosRequestConfig
  ) => {
    return await get(`/monitor/api/monitor_alert/`, {
      params,
      ...config
    });
  };

  const getInstanceList = async (
    objectId?: React.Key,
    params: InstanceParam = {},
    config?: AxiosRequestConfig
  ) => {
    return await get(`/monitor/api/monitor_instance/${String(objectId)}/list/`, {
      params,
      ...config
    });
  };

  const getEffectivePlugins = async (
    objectId?: React.Key,
    params: {
      instance_id?: string;
    } = {},
    config?: AxiosRequestConfig
  ) => {
    return await get(`/monitor/api/monitor_instance/${String(objectId)}/effective_plugins/`, {
      params,
      ...config
    });
  };

  const getMonitorPlugin = async (
    params: {
      monitor_object_id?: React.Key | null;
      /** 按监控对象分类 ID 过滤（如 database），与 monitor_object_id 互斥由调用方保证 */
      monitor_object_type?: string | null;
      // 搜索关键字(后端在 i18n 翻译完成后,对 name / display_name /
      // display_description / parent_object_display_name 做 icontains 内存匹配)
      keyword?: string;
      // 传 page_size>0 时后端返回 {count, items};不传或 -1/0 仍返回全量数组
      page?: number;
      page_size?: number;
    } = {},
    config?: AxiosRequestConfig
  ) => {
    return await get('/monitor/api/monitor_plugin/', {
      params,
      ...config
    });
  };

  const patchMonitorAlert = async (
    id: React.Key,
    data: {
      status?: string;
    }
  ) => {
    return await patch(`/monitor/api/monitor_alert/${String(id)}/`, data);
  };

  const getAllUsers = async () => {
    return await get(`/monitor/api/system_mgmt/user_all/`);
  };

  const getUnitList = async () => {
    return await get(`/monitor/api/unit/list`);
  };

  return {
    getMonitorMetrics,
    getMetricsGroup,
    getMonitorObject,
    getMonitorAlert,
    getInstanceList,
    getEffectivePlugins,
    getMonitorPlugin,
    patchMonitorAlert,
    getAllUsers,
    getUnitList
  };
};

export default useMonitorApi;
