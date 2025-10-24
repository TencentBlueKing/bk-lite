import useApiClient from '@/utils/request';

// 包管理相关类型和接口
export interface PackageParams {
  os: string;
  type: string;
  name: string;
  version: string;
  object: string;
  file: File;
}

/**
 * 包管理API Hook
 * 职责：处理包的上传、删除和列表获取
 */
const usePackageApi = () => {
  const { get, post, del } = useApiClient();

  // 获取包列表
  const getPackageList = async (params: {
    object?: string;
    os?: string;
    page?: number;
    page_size?: number;
  }) => {
    return await get('/node_mgmt/api/package', { params });
  };

  // 上传包
  const uploadPackage = async (data: PackageParams) => {
    return await post('/node_mgmt/api/package', data, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  };

  // 删除包
  const deletePackage = async (id: number) => {
    return await del(`/node_mgmt/api/package/${id}`);
  };

  return {
    getPackageList,
    uploadPackage,
    deletePackage,
  };
};

export default usePackageApi;
