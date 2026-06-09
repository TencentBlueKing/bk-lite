import useApiClient from '@/utils/request';
import { GroupFieldType } from '@/app/cmdb/types/assetManage';

export const useClassificationApi = () => {
  const { get, post, put, del } = useApiClient();

  // 获取分类列表（管理模式时传 includeHidden=true 拉全量）
  const getClassificationList = (includeHidden?: boolean) =>
    get(`/cmdb/api/classification/${includeHidden ? '?include_hidden=true' : ''}`);

  // 创建分类
  const createClassification = (params: GroupFieldType) =>
    post('/cmdb/api/classification/', params);

  // 更新分类
  const updateClassification = (classificationId: string, params: GroupFieldType) =>
    put(`/cmdb/api/classification/${classificationId}/`, params);

  // 删除分类
  const deleteClassification = (classificationId: string) =>
    del(`/cmdb/api/classification/${classificationId}/`);

  return {
    getClassificationList,
    createClassification,
    updateClassification,
    deleteClassification,
  };
};
