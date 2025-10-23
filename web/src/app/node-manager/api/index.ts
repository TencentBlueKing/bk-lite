import useApiClient from '@/utils/request';

export interface PackageParams {
  os: string;
  type: string;
  name: string;
  version: string;
  object: string;
  file: File;
}

const useApiNode = () => {
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

export default useApiNode;
