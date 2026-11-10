import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import { getStoredLocale } from '@/utils/userPreferences';
import {
  invalidateModelAttrListCache,
  loadCachedModelAttrList,
  loadCachedModelAttrListBatch,
} from './modelAttrListCache';

export const useModelApi = () => {
  const { get, post, put, del } = useApiClient();

  // 获取模型列表（管理模式时传 includeHidden=true 拉全量）
  const getModelList = useCallback((includeHidden?: boolean) =>
    get(`/cmdb/api/model/${includeHidden ? '?include_hidden=true' : ''}`), [get]);

  // 创建模型
  const createModel = (params: any) =>
    post('/cmdb/api/model/', params);

  // 更新模型
  const updateModel = (modelId: string, params: any) =>
    put(`/cmdb/api/model/${modelId}/`, params);

  // 删除模型
  const deleteModel = (modelId: string) =>
    del(`/cmdb/api/model/${modelId}/`);

  // 获取模型属性列表。同一模型的进行中请求和已返回结果在页面间共享。
  const getModelAttrList = (modelId: string) =>
    loadCachedModelAttrList(getStoredLocale(), modelId, (id) =>
      get(`/cmdb/api/model/${id}/attr_list/`));

  const getModelAttrListBatch = (modelIds: string[]) =>
    loadCachedModelAttrListBatch(getStoredLocale(), modelIds, async (ids) => {
      const payload = await post('/cmdb/api/model/attr_list/batch/', { model_ids: ids });
      return payload?.attrs || {};
    });

  // 创建模型属性
  const createModelAttr = async (modelId: string, params: any) => {
    const result = await post(`/cmdb/api/model/${modelId}/attr/`, params);
    invalidateModelAttrListCache(modelId);
    return result;
  };

  // 更新模型属性
  const updateModelAttr = async (modelId: string, params: any) => {
    const result = await put(`/cmdb/api/model/${modelId}/attr_update/`, params);
    invalidateModelAttrListCache(modelId);
    return result;
  };

  // 删除模型属性
  const deleteModelAttr = async (modelId: string, attrId: string) => {
    const result = await del(`/cmdb/api/model/${modelId}/attr/${attrId}/`);
    invalidateModelAttrListCache(modelId);
    return result;
  };

  const getModelUniqueRules = (modelId: string, editingRuleId?: string) =>
    get(`/cmdb/api/model/${modelId}/unique_rules/${editingRuleId ? `?editing_rule_id=${editingRuleId}` : ''}`.replace('/?', '?'));

  const createModelUniqueRule = (modelId: string, params: { field_ids: string[] }) =>
    post(`/cmdb/api/model/${modelId}/unique_rules/`, params);

  const updateModelUniqueRule = (modelId: string, ruleId: string, params: { field_ids: string[] }) =>
    put(`/cmdb/api/model/${modelId}/unique_rules/${ruleId}/`, params);

  const deleteModelUniqueRule = (modelId: string, ruleId: string) =>
    del(`/cmdb/api/model/${modelId}/unique_rules/${ruleId}/`);

  const getModelDuplicateRules = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/duplicate_rules/`);

  const createModelDuplicateRule = (modelId: string, params: { field_ids: string[] }) =>
    post(`/cmdb/api/model/${modelId}/duplicate_rules/`, params);

  const updateModelDuplicateRule = (modelId: string, ruleId: string, params: { field_ids: string[] }) =>
    put(`/cmdb/api/model/${modelId}/duplicate_rules/${ruleId}/`, params);

  const deleteModelDuplicateRule = (modelId: string, ruleId: string) =>
    del(`/cmdb/api/model/${modelId}/duplicate_rules/${ruleId}/`);

  const setModelAssociationRequired = (modelId: string, params: { model_asst_id: string; required: boolean }) =>
    put(`/cmdb/api/model/${modelId}/association_required/`, params);

  const getModelIslandCounts = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/island_counts/`);

  const getModelAutoAssociationRules = (modelId: string) =>
    get(`/cmdb/api/model/${modelId}/auto_association_rules/`);

  const createModelAutoAssociationRule = (modelId: string, params: {
    model_asst_id: string;
    enabled: boolean;
    match_pairs: Array<{
      src_field_id: string;
      dst_field_id: string;
    }>;
  }) => post(`/cmdb/api/model/${modelId}/auto_association_rules/`, params);

  const updateModelAutoAssociationRule = (modelId: string, modelAsstId: string, ruleId: string, params: {
    enabled: boolean;
    match_pairs: Array<{
      src_field_id: string;
      dst_field_id: string;
    }>;
  }) => put(`/cmdb/api/model/${modelId}/auto_association_rules/${modelAsstId}/${ruleId}/`, params);

  const deleteModelAutoAssociationRule = (modelId: string, modelAsstId: string, ruleId: string) =>
    del(`/cmdb/api/model/${modelId}/auto_association_rules/${modelAsstId}/${ruleId}/`);

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

  const getModelAttrGroupsFullInfo = useCallback(async (modelId: string) =>
    get(`/cmdb/api/field_groups/full_info/?model_id=${modelId}`), [get]);

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

  const exportModelConfig = async (token: string, modelIds: string[] = []) => {
    const response = await fetch('/api/proxy/cmdb/api/model/export_model_config', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model_ids: modelIds }),
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

  // 保存模型管理布局（管理员，分类排序+模型排序+可见性，一次提交）
  const saveModelLayout = (payload: {
    classifications: Array<{ classification_id: string; order: number; is_visible: boolean }>;
    models: Array<{ model_id: string; order_id: number; is_visible: boolean }>;
  }) => post('/cmdb/api/model/save_layout/', payload);

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
    getModelAttrListBatch,
    createModelAttr,
    updateModelAttr,
    deleteModelAttr,
    getModelUniqueRules,
    createModelUniqueRule,
    updateModelUniqueRule,
    deleteModelUniqueRule,
    getModelDuplicateRules,
    createModelDuplicateRule,
    updateModelDuplicateRule,
    deleteModelDuplicateRule,
    setModelAssociationRequired,
    getModelIslandCounts,
    getModelAutoAssociationRules,
    createModelAutoAssociationRule,
    updateModelAutoAssociationRule,
    deleteModelAutoAssociationRule,
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
    importModelConfig,
    saveModelLayout
  };
};
