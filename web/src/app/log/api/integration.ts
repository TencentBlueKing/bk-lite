import useApiClient from '@/utils/request';
import React from 'react';
import {
  InstanceInfo,
  IntegrationLogInstance,
} from '@/app/log/types/integration';
import { GroupInfo } from '@/app/log/types/integration';
import { cloneDeep } from 'lodash';
interface NodeConfigParam {
  configs?: any;
  collect_type?: string;
  collector?: string;
  instances?: Omit<IntegrationLogInstance, 'key'>[];
}

const useIntegrationApi = () => {
  const { get, post, put, del, patch } = useApiClient();

  const getCollectTypes = async (
    params: {
      collector?: React.Key | null;
      collect_type_id?: React.Key | null;
      add_policy_count?: boolean;
      add_instance_count?: boolean;
      name?: string;
      page?: number;
      page_size?: number;
    } = {}
  ) => {
    return await get('/log/collect_types/', {
      params,
    });
  };

  const getFields = async (params = {}) => {
    return await get('/log/collect_types/all_attrs/', {
      params,
    });
  };

  const getFieldValues = async (
    params: {
      filed?: string;
      start_time?: string;
      end_time?: string;
      limit?: number;
    } = {}
  ) => {
    return await get(`/log/search/field_names/`, {
      params,
    });
  };

  const getCollectTypesById = async (
    params: {
      collect_type_id?: React.Key | null;
    } = {}
  ) => {
    return await get(`/log/collect_types/${params.collect_type_id}`);
  };

  const batchCreateInstances = async (data: NodeConfigParam) => {
    return await post('/log/collect_instances/batch_create/', data);
  };

  const getLogNodeList = async (data: {
    cloud_region_id?: number;
    page?: number;
    page_size?: number;
    is_active?: boolean;
  }) => {
    return await post('/log/node_mgmt/nodes/', data);
  };

  const getInstanceList = async (data: {
    collect_type_id?: React.Key;
    page?: number;
    page_size?: number;
    name?: string;
  }) => {
    return await post('/log/collect_instances/search/', data);
  };

  const getInstanceChildConfig = async (data: {
    instance_id?: string | number;
    instance_type?: string;
  }) => {
    return await post(`/log/api/node_mgmt/get_instance_asso_config/`, data);
  };

  const deleteLogInstance = async (data: {
    instance_ids: any;
    clean_child_config: boolean;
  }) => {
    return await post(`/log/collect_instances/remove_collect_instance/`, data);
  };

  const updateMonitorInstance = async (data: InstanceInfo) => {
    return await post('/log/collect_instances/instance_update/', data);
  };

  const setInstancesGroup = async (data: {
    instance_ids: React.Key[];
    organizations: React.Key[];
  }) => {
    return await post(`/log/collect_instances/set_organizations/`, data);
  };

  const getConfigContent = async (data: { ids: React.Key[] }) => {
    return await post('/log/collect_configs/get_config_content/', data);
  };

  const updateInstanceCollectConfig = async (data: {
    instance_id?: React.Key;
    collect_type_id?: React.Key;
    child: {
      id: string;
      content_data: any;
    };
  }) => {
    return await post(
      `/log/collect_configs/update_instance_collect_config/`,
      data
    );
  };

  const createLogStreams = async (data: GroupInfo) => {
    return await post(`/log/log_group/`, data);
  };

  const updateLogStreams = async (data: GroupInfo) => {
    const params = cloneDeep(data);
    delete params.id;
    return await put(`/log/log_group/${data.id}/`, params);
  };

  const updateDefaultLogStreams = async (data: GroupInfo) => {
    const params = cloneDeep(data);
    delete params.id;
    return await patch(`/log/log_group/${data.id}/`, params);
  };

  const getLogStreams = async (
    params: {
      name?: string;
      page?: number;
      page_size?: number;
      collect_type_id?: React.Key;
    } = {}
  ) => {
    return await get('/log/log_group/', {
      params,
    });
  };

  const deleteLogStream = async (id: React.Key) => {
    return await del(`/log/log_group/${id}/`);
  };

  return {
    getCollectTypes,
    getLogNodeList,
    batchCreateInstances,
    getInstanceList,
    getInstanceChildConfig,
    deleteLogInstance,
    updateMonitorInstance,
    setInstancesGroup,
    getConfigContent,
    updateInstanceCollectConfig,
    getLogStreams,
    createLogStreams,
    updateLogStreams,
    deleteLogStream,
    updateDefaultLogStreams,
    getCollectTypesById,
    getFields,
    getFieldValues,
  };
};

export default useIntegrationApi;
