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

  const getModelUniqueRules = (modelId: string, editingRuleId?: string) =>
    get(`/cmdb/api/model/${modelId}/unique_rules/${editingRuleId ? `?editing_rule_id=${editingRuleId}` : ''}`.replace('/?', '?'));

  const createModelUniqueRule = (modelId: string, params: { field_ids: string[] }) =>
    post(`/cmdb/api/model/${modelId}/unique_rules/`, params);

  const updateModelUniqueRule = (modelId: string, ruleId: string, params: { field_ids: string[] }) =>
    put(`/cmdb/api/model/${modelId}/unique_rules/${ruleId}/`, params);

  const deleteModelUniqueRule = (modelId: string, ruleId: string) =>
    del(`/cmdb/api/model/${modelId}/unique_rules/${ruleId}/`);

  // 获取模型关联列表
  const getModelAssociations = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/association/`);

  // 创建模型关联
  const createModelAssociation = (params: any) =>
    post('/cmdb/api/model/association/', params);

  // 删除模型关联
  const deleteModelAssociation = (associationId: string) =>
    del(`/cmdb/api/model/association/${associationId}/`);

  const batchDeleteModelAssociations = (associationIds: string[]) =>
    post('/cmdb/api/model/association/batch_delete/', {
      model_asst_ids: associationIds,
    });

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

  const exportModelConfig = async (token: string) => {
    const response = await fetch('/api/proxy/cmdb/api/model/export_model_config', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || 'Export failed');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'model_config.xlsx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  // 导入模型配置
  const importModelConfig = async (file: File, token: string) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch('/api/proxy/cmdb/api/model/import_model_config/', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || 'Import failed');
    }
    return response.json();
  };

  // ========== 公共枚举库 API ==========
  // 获取公共枚举库列表
  const getPublicEnumLibraries = () =>
    get('/cmdb/api/public_enum_libraries/');

  // 创建公共枚举库
  const createPublicEnumLibrary = (params: {
    name: string;
    team: (string | number)[];
    options: { id: string; name: string }[];
  }) => post('/cmdb/api/public_enum_libraries/', params);

  // 更新公共枚举库
  const updatePublicEnumLibrary = (
    libraryId: string,
    params: {
      name?: string;
      team?: (string | number)[];
      options?: { id: string; name: string }[];
    }
  ) => put(`/cmdb/api/public_enum_libraries/${libraryId}/`, params);

  // 删除公共枚举库
  const deletePublicEnumLibrary = (libraryId: string) =>
    del(`/cmdb/api/public_enum_libraries/${libraryId}/`);

  // 获取公共枚举库引用列表
  const getPublicEnumLibraryReferences = (libraryId: string) =>
    get(`/cmdb/api/public_enum_libraries/${libraryId}/references/`);

  return {
    getModelList,
    createModel,
    updateModel,
    deleteModel,
    getModelAttrList,
    createModelAttr,
    updateModelAttr,
    deleteModelAttr,
    getModelUniqueRules,
    createModelUniqueRule,
    updateModelUniqueRule,
    deleteModelUniqueRule,
    getModelAssociations,
    createModelAssociation,
    deleteModelAssociation,
    batchDeleteModelAssociations,
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
    copyModel,
    getPublicEnumLibraries,
    createPublicEnumLibrary,
    updatePublicEnumLibrary,
    deletePublicEnumLibrary,
    getPublicEnumLibraryReferences,
    exportModelConfig,
    importModelConfig
  };
};
