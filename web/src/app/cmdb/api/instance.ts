import useApiClient from '@/utils/request';

export const useInstanceApi = () => {
  const { get, post, patch, del } = useApiClient();

  // 搜索实例
  const searchInstances = (params: any) =>
    post('/cmdb/api/instance/search/', params);

  // 全文搜索实例
  const fulltextSearchInstances = (params: any) =>
    post('/cmdb/api/instance/fulltext_search/', params);

  const fulltextSearchStats = (params: any) =>
    post('/cmdb/api/instance/fulltext_search/stats/', params);

  const fulltextSearchByModel = (params: any) =>
    post('/cmdb/api/instance/fulltext_search/by_model/', params);

  const topoSearchInstances = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/topo_search/${modelId}/${instId}/`);

  const getTopoThemes = (modelId: string) =>
    get(`/cmdb/api/instance/topo_themes/${modelId}/`);

  const getNetworkTopo = (modelId: string, instId: string, depth?: number) =>
    get(
      `/cmdb/api/instance/network_topo/${modelId}/${instId}/${
        depth ? `?depth=${depth}` : ''
      }`
    );

  const getRoomLayout = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/room_layout/${modelId}/${instId}/`);

  const getRackLayout = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/rack_layout/${modelId}/${instId}/`);

  const getApplicationResourceApps = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/application_resource_apps/${modelId}/${instId}/`);

  const getApplicationResourceTopology = (
    modelId: string,
    instId: string,
    depth = 1
  ) => get(`/cmdb/api/instance/application_resource_topology/${modelId}/${instId}/?depth=${depth}`);

  const getApplicationResourceResources = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/application_resource_resources/${modelId}/${instId}/`);

  // 获取实例详情
  const getInstanceDetail = (instanceId: string) =>
    get(`/cmdb/api/instance/${instanceId}/`);

  // 创建实例
  const createInstance = (params: any) =>
    post('/cmdb/api/instance/', params);

  // 更新实例
  const updateInstance = (instanceId: string, params: any) =>
    patch(`/cmdb/api/instance/${instanceId}/`, params);

  // 批量更新实例
  const batchUpdateInstances = (params: any) =>
    post('/cmdb/api/instance/batch_update/', params);

  // 删除实例
  const deleteInstance = (instanceId: string) =>
    del(`/cmdb/api/instance/${instanceId}/`);

  // 批量删除实例
  const batchDeleteInstances = (instanceIds: string[]) =>
    post('/cmdb/api/instance/batch_delete/', instanceIds);

  // 获取实例代理列表
  const getInstanceProxys = (params?: any) =>
    get('/cmdb/api/instance/list_proxys/', { params });

  // 获取模型实例数量
  const getModelInstanceCount = () =>
    get('/cmdb/api/instance/model_inst_count/');

  // 获取实例显示字段详情
  const getInstanceShowFieldDetail = (modelId: string) =>
    get(`/cmdb/api/instance/${modelId}/show_field/detail/`);

  // 设置实例显示字段
  const setInstanceShowFieldSettings = (modelId: string, fields: any) =>
    post(`/cmdb/api/instance/${modelId}/show_field/settings/`, fields);

  // 获取关联实例列表
  const getAssociationInstanceList = (modelId: string, instId: string) =>
    get(`/cmdb/api/instance/association_instance_list/${modelId}/${instId}/`);

  // 拓扑搜索更多实例
  const topoSearchMore = (params: { model_id: string, inst_id: string, parent_id: string[] }) =>
    post('/cmdb/api/instance/topo_search_expand/', params);


  // 创建实例关联
  const createInstanceAssociation = (params: any) =>
    post('/cmdb/api/instance/association/', params);

  // 删除实例关联
  const deleteInstanceAssociation = (associationId: string) =>
    del(`/cmdb/api/instance/association/${associationId}/`);

  // 导入实例
  const importInstances = (modelId: string, formData: FormData, options?: any) =>
    post(`/cmdb/api/instance/${modelId}/inst_import/`, formData, options);

  // 下载模板
  const downloadTemplate = (modelId: string) => ({
    url: `/api/proxy/cmdb/api/instance/${modelId}/download_template/`,
    method: 'GET'
  });

  // 附件/图片字段（企业版）：预上传文件（multipart: file, model_id, attr_id），返回文件元数据
  // 必须显式指定 multipart，否则 axios 默认 JSON 头会把 FormData 转成 JSON（File 丢失）
  const uploadFile = (formData: FormData, options?: any) =>
    post('/cmdb/api/instance/upload_file/', formData, {
      ...(options || {}),
      headers: { 'Content-Type': 'multipart/form-data', ...(options?.headers || {}) },
    });

  // 删除尚未提交的临时文件（仅上传者本人）
  const deleteFile = (fileId: string) =>
    del(`/cmdb/api/instance/delete_file/${fileId}/`);

  // 获取附件/图片的短时效预签名直链（经 axios 带令牌鉴权；返回 { url }）
  // download=true 时返回的 URL 附带 attachment disposition，浏览器打开即触发下载保存
  const getFileUrl = (fileId: string, download = false): Promise<{ url: string }> =>
    get(`/cmdb/api/instance/download_file/${fileId}/${download ? '?download=1' : ''}`);

  // 获取 IPAM 子网 IP 视图矩阵数据
  const getIpamView = (instId: string) =>
    get(`/cmdb/api/instance/ipam_view/${instId}/`);

  return {
    searchInstances,
    fulltextSearchInstances,
    fulltextSearchStats,
    fulltextSearchByModel,
    topoSearchInstances,
    getTopoThemes,
    getNetworkTopo,
    getRoomLayout,
    getRackLayout,
    getApplicationResourceApps,
    getApplicationResourceTopology,
    getApplicationResourceResources,
    getInstanceDetail,
    createInstance,
    updateInstance,
    batchUpdateInstances,
    deleteInstance,
    batchDeleteInstances,
    getInstanceProxys,
    getModelInstanceCount,
    getInstanceShowFieldDetail,
    setInstanceShowFieldSettings,
    getAssociationInstanceList,
    topoSearchMore,
    createInstanceAssociation,
    deleteInstanceAssociation,
    importInstances,
    downloadTemplate,
    uploadFile,
    deleteFile,
    getFileUrl,
    getIpamView,
  };
};
