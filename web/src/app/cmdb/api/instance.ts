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

  const topoSearchInstances = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/topo_search/${modelId}/${instUuid}/`);

  const getTopoThemes = (modelId: string) =>
    get(`/cmdb/api/instance/topo_themes/${modelId}/`);

  const getNetworkTopo = (modelId: string, instUuid: string, depth?: number) =>
    get(
      `/cmdb/api/instance/network_topo/${modelId}/${instUuid}/${
        depth ? `?depth=${depth}` : ''
      }`
    );

  const getRoomLayout = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/room_layout/${modelId}/${instUuid}/`);

  const getRackLayout = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/rack_layout/${modelId}/${instUuid}/`);

  const getApplicationResourceApps = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/application_resource_apps/${modelId}/${instUuid}/`);

  const getApplicationResourceTopology = (
    modelId: string,
    instUuid: string,
    depth = 1
  ) => get(`/cmdb/api/instance/application_resource_topology/${modelId}/${instUuid}/?depth=${depth}`);

  const getApplicationResourceResources = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/application_resource_resources/${modelId}/${instUuid}/`);

  const getApplicationResourceInstances = (
    modelId: string,
    instUuid: string,
    nodeUuids: string[]
  ) => post(
    `/cmdb/api/instance/application_resource_instances/${modelId}/${instUuid}/`,
    { node_uuids: nodeUuids }
  );

  const exportApplicationResourceInstances = (
    modelId: string,
    instUuid: string,
    nodeUuids: string[]
  ) => post(
    `/cmdb/api/instance/application_resource_export/${modelId}/${instUuid}/`,
    { node_uuids: nodeUuids },
    { responseType: 'blob' }
  );

  // 获取实例详情
  const getInstanceDetail = (instUuid: string) =>
    get(`/cmdb/api/instance/${instUuid}/`);

  // 创建实例
  const createInstance = (params: any) =>
    post('/cmdb/api/instance/', params);

  // 更新实例
  const updateInstance = (instUuid: string, params: any) =>
    patch(`/cmdb/api/instance/${instUuid}/`, params);

  // 批量更新实例
  const batchUpdateInstances = (params: {
    inst_uuids: string[];
    update_data: Record<string, unknown>;
  }) => post('/cmdb/api/instance/batch_update/', params);

  // 删除实例
  const deleteInstance = (instUuid: string) =>
    del(`/cmdb/api/instance/${instUuid}/`);

  // 批量删除实例
  const batchDeleteInstances = (instUuids: string[]) =>
    post('/cmdb/api/instance/batch_delete/', { inst_uuids: instUuids });

  // 获取实例代理列表
  const getInstanceProxys = (params?: any) =>
    get('/cmdb/api/instance/list_proxys/', { params });

  const pushToMonitor = (instUuid: string) =>
    post(`/cmdb/api/instance/${instUuid}/push_to_monitor/`);

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
  const getAssociationInstanceList = (modelId: string, instUuid: string) =>
    get(`/cmdb/api/instance/association_instance_list/${modelId}/${instUuid}/`);

  // 拓扑搜索更多实例
  const topoSearchMore = (params: {
    model_id: string;
    inst_uuid: string;
    parent_uuid: string[];
  }) => post('/cmdb/api/instance/topo_search_expand/', params);


  // 创建实例关联
  const createInstanceAssociation = (params: {
    model_asst_id: string;
    src_model_id?: string;
    dst_model_id?: string;
    asst_id?: string;
    src_inst_uuid: string;
    dst_inst_uuid: string;
    [key: string]: unknown;
  }) => post('/cmdb/api/instance/association/', params);

  // 删除实例关联（业务键：源/目标 UUID + model_asst_id）
  const deleteInstanceAssociation = (
    srcInstUuid: string,
    dstInstUuid: string,
    modelAsstId: string
  ) =>
    del(
      `/cmdb/api/instance/association/${srcInstUuid}/${dstInstUuid}/${modelAsstId}/`
    );

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
  const getIpamView = (instUuid: string) =>
    get(`/cmdb/api/instance/ipam_view/${instUuid}/`);

  const saveIpamIp = (params: {
    subnet_inst_uuid: string;
    ip_addr: string;
    ip_allocated_status: string;
    ip_status?: string;
    ip_type?: string;
    ip_user?: string[];
    mac?: string;
    description?: string;
  }) => post('/cmdb/api/instance/ipam_ip/', params);

  const saveRackRoomLayout = (params: {
    action: string;
    scope: 'room' | 'rack';
    container_inst_uuid: string;
    inst_uuid?: string;
    model_id?: string;
    instance_info?: Record<string, unknown>;
    row?: number;
    col?: number;
    u_start?: number;
    u_size?: number;
  }) => post('/cmdb/api/instance/rack_room_layout/', params);

  const getRackRoomLayoutCandidates = (params: {
    scope: 'room' | 'rack';
    container_inst_uuid: string;
    model_id: string;
    page?: number;
    page_size?: number;
    search?: string;
  }) => get('/cmdb/api/instance/rack_room_layout_candidates/', { params });

  const getRacksGroupedByRoom = (params: {
    search?: string;
    page?: number;
    page_size?: number;
  }) => get('/cmdb/api/instance/racks_grouped_by_room/', { params });

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
    getApplicationResourceInstances,
    exportApplicationResourceInstances,
    getInstanceDetail,
    createInstance,
    updateInstance,
    batchUpdateInstances,
    deleteInstance,
    batchDeleteInstances,
    getInstanceProxys,
    pushToMonitor,
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
    saveIpamIp,
    saveRackRoomLayout,
    getRackRoomLayoutCandidates,
    getRacksGroupedByRoom,
  };
};
