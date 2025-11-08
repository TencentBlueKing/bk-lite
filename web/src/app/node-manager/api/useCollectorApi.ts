import useApiClient from '@/utils/request';

export interface CollectorParams {
  id: string;
  name: string;
  service_type: string;
  executable_path: string;
  execute_parameters: string;
  node_operating_system: string;
  introduction?: string;
}

/**
 * 采集器管理API Hook
 * 职责：处理采集器的CRUD操作
 */
const useCollectorApi = () => {
  const { get, post, del, put } = useApiClient();

  // 获取采集器列表
  const getCollectorlist = async ({
    search,
    node_operating_system,
    name,
    page,
    page_size,
    tags,
  }: {
    search?: string;
    node_operating_system?: string;
    name?: string;
    page?: number;
    page_size?: number;
    tags?: string;
  }) => {
    return await get('/node_mgmt/api/collector/', {
      params: { search, node_operating_system, name, page, page_size, tags },
    });
  };

  // 获取采集器详情
  const getCollectorDetail = async ({ id }: { id: string }) => {
    return await get(`/node_mgmt/api/collector/${id}`);
  };

  // 添加采集器
  const addCollector = async (params: CollectorParams) => {
    return await post('/node_mgmt/api/collector/', params);
  };

  // 删除采集器
  const deleteCollector = async ({ id }: { id: string }) => {
    return await del(`/node_mgmt/api/collector/${id}`);
  };

  // 编辑采集器
  const editCollecttor = async (params: CollectorParams) => {
    return await put(`/node_mgmt/api/collector/${params.id}`, params);
  };

  return {
    getCollectorlist,
    getCollectorDetail,
    addCollector,
    deleteCollector,
    editCollecttor,
  };
};

export default useCollectorApi;
