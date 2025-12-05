import useApiClient from '@/utils/request';

export const useCollectApi = () => {
  const { get, post, put, del } = useApiClient();

  // 获取收集任务列表
  const getCollectList = (params?: any) =>
    get('/cmdb/api/collect/search/', { params });

  // 获取收集任务详情
  const getCollectDetail = (collectId: string) =>
    get(`/cmdb/api/collect/${collectId}/`);

  // 创建收集任务
  const createCollect = (params: any) =>
    post('/cmdb/api/collect/', params);

  // 更新收集任务
  const updateCollect = (collectId: string, params: any) =>
    put(`/cmdb/api/collect/${collectId}/`, params);

  // 删除收集任务
  const deleteCollect = (collectId: string) =>
    del(`/cmdb/api/collect/${collectId}/`);

  // 执行收集任务
  const executeCollect = (collectId: string) =>
    post(`/cmdb/api/collect/${collectId}/exec_task/`);


  // 获取收集任务信息
  const getCollectInfo = (collectId: string) =>
    get(`/cmdb/api/collect/${collectId}/info/`);

  // 获取收集模型树
  const getCollectModelTree = () =>
    get('/cmdb/api/collect/collect_model_tree/');

  // 获取模型实例
  const getCollectModelInstances = (params?: any) =>
    get('/cmdb/api/collect/model_instances/', { params });

  // 获取收集节点
  const getCollectNodes = (params?: any) =>
    get('/cmdb/api/collect/nodes/', { params });

  // 获取区域列表
  const getCollectRegions = (params: any) =>
    post('/cmdb/api/collect/list_regions', params);

  // 获取插件文档
  const getCollectModelDoc = (id: string) =>
    get('/cmdb/api/collect/collect_model_doc', { params: { id } });

  // 获取任务状态统计
  const getTaskStatus = () =>
    get('/cmdb/api/collect/task_status');

  return {
    getCollectList,
    getCollectDetail,
    createCollect,
    updateCollect,
    deleteCollect,
    executeCollect,
    getCollectInfo,
    getCollectModelTree,
    getCollectModelInstances,
    getCollectNodes,
    getCollectRegions,
    getCollectModelDoc,
    getTaskStatus,
  };
};
