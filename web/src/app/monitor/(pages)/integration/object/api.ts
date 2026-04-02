import useApiClient from '@/utils/request';
import {
  MonitorObjectType,
  MonitorObjectItem,
  GetObjectsParams,
  ObjectTypeFormData,
  ObjectFormData
} from './types';

const useObjectApi = () => {
  const { get, post, patch, del } = useApiClient();

  // ============ 对象类型 API ============

  // 获取对象类型列表
  const getObjectTypes = async (): Promise<MonitorObjectType[]> => {
    const res = await get('/monitor/api/monitor_object_type/');
    // 显示名称优先级：display_name（国际化） > name（用户输入） > id
    return (res || []).map((item: any) => ({
      ...item,
      name: item.display_name || item.name || item.id
    }));
  };

  // 创建对象类型
  const createObjectType = async (
    data: ObjectTypeFormData
  ): Promise<MonitorObjectType> => {
    // 前端传 id 和 name
    return await post('/monitor/api/monitor_object_type/', {
      id: data.id,
      name: data.name
    });
  };

  // 更新对象类型
  const updateObjectType = async (
    id: string,
    data: Partial<ObjectTypeFormData>
  ): Promise<MonitorObjectType> => {
    // 更新时只传 name
    return await patch(`/monitor/api/monitor_object_type/${id}/`, {
      name: data.name
    });
  };

  // 删除对象类型
  const deleteObjectType = async (id: string): Promise<void> => {
    return await del(`/monitor/api/monitor_object_type/${id}/`);
  };

  // 更新对象类型排序（通过监控对象排序接口实现）
  const updateObjectTypeOrder = async (
    orderData: { type: string; object_list: string[] }[]
  ): Promise<void> => {
    return await post('/monitor/api/monitor_object/order/', orderData);
  };

  // ============ 对象 API ============

  // 获取对象列表
  const getObjects = async (
    params: GetObjectsParams = {},
    signal?: AbortSignal
  ): Promise<{ results: MonitorObjectItem[]; count: number }> => {
    const queryParams: Record<string, any> = {};

    if (params.type_id) {
      queryParams.type = params.type_id;
    }
    if (params.name) {
      queryParams.name = params.name;
    }
    if (params.page) {
      queryParams.page = params.page;
    }
    if (params.page_size) {
      queryParams.page_size = params.page_size;
    }

    const res = await get('/monitor/api/monitor_object/', {
      params: queryParams,
      signal
    });

    // 后端返回的是数组，转换为分页格式
    if (Array.isArray(res)) {
      // 转换数据格式以匹配前端期望的字段
      const results = res.map((item: any) => ({
        ...item,
        type_id: item.type,
        display_name: item.display_name || item.name
        // children_count 由后端返回，不要覆盖
      }));

      return {
        results,
        count: results.length
      };
    }

    return res;
  };

  // 获取单个对象详情
  const getObjectDetail = async (id: number): Promise<MonitorObjectItem> => {
    const res = await get(`/monitor/api/monitor_object/${id}/`);
    return {
      ...res,
      type_id: res.type,
      display_name: res.display_name || res.name
    };
  };

  // 获取对象的子对象列表
  const getObjectChildren = async (parentId: number): Promise<any[]> => {
    const res = await get('/monitor/api/monitor_object/', {
      params: { parent: parentId }
    });
    const items = Array.isArray(res) ? res : res?.results || [];
    return items.map((item: any) => ({
      id: item.name,
      name: item.display_name || item.name,
      _isExisting: true // 标记为已存在的子对象
    }));
  };

  // 创建对象（支持同时创建子对象）
  const createObject = async (
    data: ObjectFormData
  ): Promise<MonitorObjectItem> => {
    const postData: Record<string, any> = {
      name: data.name,
      display_name: data.display_name || data.name,
      icon: data.icon || '',
      type: data.type_id,
      description: data.description || '',
      level: 'base',
      is_visible: true
    };

    // 如果有子对象，一并传给后端
    if (data.children && data.children.length > 0) {
      postData.children = data.children.filter((c) => c.id && c.name);
    }

    return await post('/monitor/api/monitor_object/', postData);
  };

  // 更新对象
  const updateObject = async (
    id: number,
    data: Partial<ObjectFormData>
  ): Promise<MonitorObjectItem> => {
    const patchData: Record<string, any> = {};

    if (data.name !== undefined) patchData.name = data.name;
    if (data.display_name !== undefined)
      patchData.display_name = data.display_name;
    if (data.icon !== undefined) patchData.icon = data.icon;
    if (data.type_id !== undefined) patchData.type = data.type_id;
    if (data.description !== undefined)
      patchData.description = data.description;

    // 传递子对象（更新名称或新增）
    if (data.children !== undefined) {
      patchData.children = data.children.filter((c) => c.id && c.name);
    }

    return await patch(`/monitor/api/monitor_object/${id}/`, patchData);
  };

  // 删除对象
  const deleteObject = async (id: number): Promise<void> => {
    return await del(`/monitor/api/monitor_object/${id}/`);
  };

  // 更新对象可见性
  const updateObjectVisibility = async (
    id: number,
    isVisible: boolean
  ): Promise<void> => {
    return await post(`/monitor/api/monitor_object/${id}/visibility/`, {
      is_visible: isVisible
    });
  };

  // 更新对象排序
  const updateObjectOrder = async (
    orderData: { type: string; object_list: string[] }[]
  ): Promise<void> => {
    return await post('/monitor/api/monitor_object/order/', orderData);
  };

  return {
    // 对象类型
    getObjectTypes,
    createObjectType,
    updateObjectType,
    deleteObjectType,
    updateObjectTypeOrder,
    // 对象
    getObjects,
    getObjectDetail,
    getObjectChildren,
    createObject,
    updateObject,
    deleteObject,
    updateObjectVisibility,
    updateObjectOrder
  };
};

export default useObjectApi;
