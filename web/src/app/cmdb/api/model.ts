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

  // 获取模型属性分组列表
  const getModelAttrGroups = async (modelId: string) => get(`/cmdb/api/field_groups/?model_id=${modelId}`);

  const getModelAttrGroupsFullInfo = async (modelId: string) => get(`/cmdb/api/field_groups/full_info/?model_id=${modelId}`);

  // 创建属性分组
  const createModelAttrGroup = async (params: { model_id: string; group_name: string }) => {
    return post('/cmdb/api/field_groups/', params);
  };

  // 更新属性分组
  const updateModelAttrGroup = async (groupId: number | string, params: { group_name: string }) => {
    return put(`/cmdb/api/field_groups/${groupId}/`, params);
  };

  // 删除属性分组
  const deleteModelAttrGroup = async (groupId: number | string) => {
    return del(`/cmdb/api/field_groups/${groupId}/`);
  };

  const moveModelAttrGroup = async (groupId: number | string, direction: 'up' | 'down') => {
    return post(`/cmdb/api/field_groups/${groupId}/move/`, { direction });
  };

  const reorderGroupAttrs = async (params: {
    model_id: string;
    group_name: string;
    attr_orders: string[];
  }) => {
    return post('/cmdb/api/field_groups/reorder_group_attrs/', params);
  };

  const moveAttrToGroup = async (params: {
    model_id: string;
    attr_id: string;
    group_name: string;
    order_id: number;
  }) => {
    return post('/cmdb/api/field_groups/update_attr_group/', params);
  };

  // 复制模型
  const copyModel = (modelId: string, params: any) =>
    post(`/cmdb/api/model/${modelId}/copy/`, params);

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
    getModelDetail,
    getModelAttrGroups,
    getModelAttrGroupsFullInfo,
    createModelAttrGroup,
    updateModelAttrGroup,
    deleteModelAttrGroup,
    moveModelAttrGroup,
    reorderGroupAttrs,
    moveAttrToGroup,
    copyModel
  };
};
