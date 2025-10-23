import useApiClient from '@/utils/request';

export const useModelApi = () => {
  const { get, post, put, del } = useApiClient();

  // 获取模型列表
  const getModelList = () =>
    get('/cmdb/api/model/');

  // 创建模型
  const createModel = (params: any) =>
    post('/cmdb/api/model/', params);

  // 更新模型
  const updateModel = (modelId: string, params: any) =>
    put(`/cmdb/api/model/${modelId}/`, params);

  // 删除模型
  const deleteModel = (modelId: string) =>
    del(`/cmdb/api/model/${modelId}/`);

  // 获取模型属性列表
  const getModelAttrList = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/attr_list/`);

  // 创建模型属性
  const createModelAttr = (modelId: string, params: any) =>
    post(`/cmdb/api/model/${modelId}/attr/`, params);

  // 更新模型属性
  const updateModelAttr = (modelId: string, params: any) => 
    put(`/cmdb/api/model/${modelId}/attr_update/`, params);

  // 删除模型属性
  const deleteModelAttr = (modelId: string, attrId: string) =>
    del(`/cmdb/api/model/${modelId}/attr/${attrId}/`);

  // 获取模型关联列表
  const getModelAssociations = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/association/`);

  // 创建模型关联
  const createModelAssociation = (params: any) =>
    post('/cmdb/api/model/association/', params);

  // 删除模型关联
  const deleteModelAssociation = (associationId: string) =>
    del(`/cmdb/api/model/association/${associationId}/`);

  // 获取模型关联类型列表
  const getModelAssociationTypes = () =>
    get('/cmdb/api/model/model_association_type/');

  const getModelDetail = (modelId: string) =>
    get(`/cmdb/api/model/get_model_info/${modelId}/`);

  return {
    getModelList,
    createModel,
    updateModel,
    deleteModel,
    getModelAttrList,
    createModelAttr,
    updateModelAttr,
    deleteModelAttr,
    getModelAssociations,
    createModelAssociation,
    deleteModelAssociation,
    getModelAssociationTypes,
    getModelDetail
  };
};
