import useApiClient from '@/utils/request';

interface CollectorParams {
  id: string,
  name: string,
  service_type: string,
  executable_path: string,
  execute_parameters: string,
  node_operating_system: string,
  introduction?: string,
}

interface PackageParams {
  os: string,
  type: string,
  name: string,
  version: string,
  object: string,
  file: File
}

const useApiCollector = () => {
  const { get, post, del, put } = useApiClient();

  //获取采集器列表
  const getCollectorlist = async ({
    search,
    node_operating_system,
    name,
    page,
    page_size,
  }: {
    search?: string,
    node_operating_system?: string,
    name?: string,
    page?: number,
    page_size?: number
  }) => {
    return await get('/node_mgmt/api/collector/', {
      params: { search, node_operating_system, name, page, page_size },
    });
  };

  // 获取采集器详情
  const getCollectorDetail = async ({
    id
  }: {
    id: string
  }) => {
    return await get(`/node_mgmt/api/collector/${id}`);
  };

  // 获取控制器列表
  const getControllerList = async ({
    name,
    search,
    os,
    page,
    page_size,
  }: {
    name?: string,
    search?: string,
    os?: string,
    page?: number,
    page_size?: number,
  }) => {
    return await get('/node_mgmt/api/controller/', {
      params: { search, os, name, page, page_size }
    });

  };

  // 添加采集器
  const addCollector = async (params: CollectorParams) => {
    return await post('/node_mgmt/api/collector/', params)
  };

  // 删除采集器
  const deleteCollector = async ({
    id
  }: {
    id: string
  }) => {
    return await del(`/node_mgmt/api/collector/${id}`)
  };

  // 编辑采集器
  const editCollecttor = async (params: CollectorParams) => {
    return await put(`/node_mgmt/api/collector/${params.id}`, params);
  };

  // 获取包列表
  const getPackageList = async (params: { object?: string; os?: string; }) => {
    return await get('/node_mgmt/api/package',{ params });
  }

  // 上传包
  const uploadPackage = async (data: PackageParams) => {
    return await post('/node_mgmt/api/package', data,{
      headers: {
        "Content-Type": "multipart/form-data"
      }
    })
  };

  // 删除包
  const deletePackage = async (id: number) => {
    return await del(`/node_mgmt/api/package/${id}`);
  };

  return {
    getCollectorlist,
    getCollectorDetail,
    getControllerList,
    addCollector,
    deleteCollector,
    editCollecttor,
    uploadPackage,
    getPackageList,
    deletePackage
  };
};

export default useApiCollector;
