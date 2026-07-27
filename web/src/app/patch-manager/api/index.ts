import useApiClient from '@/utils/request';
import { AxiosRequestConfig } from 'axios';
import {
  ListResponse,
  Patch,
  PatchDashboardStats,
  PatchSource,
  PatchSourceParams,
  PatchTarget,
  PatchTargetParams,
  PatchParams,
  CandidateItem,
  IngestResult,
  ScanSetting,
} from '@/app/patch-manager/types';

const BASE = '/patch_mgmt/api';

const usePatchManagerApi = () => {
  const { get, post, put, patch, del } = useApiClient();

  // ── 补丁源 ──────────────────────────────────────────────────────────────────

  const getPatchSourceList = async (
    params: PatchSourceParams = {},
    config?: AxiosRequestConfig
  ): Promise<ListResponse<PatchSource>> =>
    get(`${BASE}/patch_source/`, { params, ...config });

  const createPatchSource = async (data: Partial<PatchSource>): Promise<PatchSource> =>
    post(`${BASE}/patch_source/`, data);

  const testPatchSourceConnectivity = async (data: Partial<PatchSource>): Promise<{
    connectivity_status: string; detail: string; status_code: number | null;
  }> => post(`${BASE}/patch_source/test_connectivity/`, data, { timeout: 20000 });

  const testExistingPatchSourceConnectivity = async (
    id: number,
    data: Partial<PatchSource>,
  ): Promise<{ connectivity_status: string; detail: string; status_code: number | null }> =>
    post(`${BASE}/patch_source/${id}/check_connectivity/`, data, { timeout: 20000 });

  const updatePatchSource = async (id: number, data: Partial<PatchSource>): Promise<PatchSource> =>
    patch(`${BASE}/patch_source/${id}/`, data);

  const deletePatchSource = async (id: number): Promise<void> =>
    del(`${BASE}/patch_source/${id}/`);

  const setPatchSourceEnabled = async (id: number, isEnabled: boolean): Promise<PatchSource> =>
    post(`${BASE}/patch_source/${id}/set_enabled/`, { is_enabled: isEnabled });

  // 批量探测补丁源连通性；单个探测也走此接口，传 [id]
  const checkPatchSourceConnectivity = async (
    sourceIds: number[]
  ): Promise<Array<{ source_id: number; connectivity_status: string; last_checked_at: string | null }>> =>
    post(`${BASE}/patch_source/check_connectivity/`, { source_ids: sourceIds }, { timeout: 60000 });

  // 同步补丁源到补丁库(Linux yum/dnf 元数据);同步执行,超时放宽到 60s
  const syncPatchSource = async (
    id: number
  ): Promise<{ total: number; created: number; updated: number }> =>
    post(`${BASE}/patch_source/${id}/sync/`, undefined, { timeout: 60000 });

  // 预览补丁源候选补丁（不写库），供「同步入库」抽屉展示
  const previewSyncPatchSource = async (
    id: number,
    params: { search?: string; page?: number; page_size?: number }
  ): Promise<{ items: CandidateItem[]; total: number; page: number; page_size: number }> =>
    post(`${BASE}/patch_source/${id}/preview_sync/`, params, { timeout: 60000 });

  // 将选中的候选补丁入库
  const ingestPatchSource = async (
    id: number,
    keys: string[],
    severityOverrides?: Record<string, string>
  ): Promise<IngestResult> =>
    post(`${BASE}/patch_source/${id}/ingest/`, { keys, severity_overrides: severityOverrides }, { timeout: 120000 });

  // ── 补丁库 ──────────────────────────────────────────────────────────────────

  const getPatchList = async (
    params: PatchParams = {},
    config?: AxiosRequestConfig
  ): Promise<ListResponse<Patch>> =>
    get(`${BASE}/patch/`, { params, ...config });

  const getPatchDetail = async (id: number): Promise<Patch> =>
    get(`${BASE}/patch/${id}/`);

  const createPatch = async (data: Partial<Patch>): Promise<Patch> =>
    post(`${BASE}/patch/`, data);

  const uploadWindowsPatchPackage = async (id: number, file: File, replace = false): Promise<Patch> => {
    const body = new FormData();
    body.append('file', file);
    return post(`${BASE}/patch/${id}/${replace ? 'replace_package' : 'upload_package'}/`, body, {
      headers: { 'Content-Type': undefined },
      timeout: 0,
    });
  };

  const updatePatch = async (id: number, data: Partial<Patch>): Promise<Patch> =>
    put(`${BASE}/patch/${id}/`, data);

  const deletePatch = async (id: number): Promise<void> =>
    del(`${BASE}/patch/${id}/`);

  // ── 目标管理 ────────────────────────────────────────────────────────────────

  const getPatchTargetList = async (
    params: PatchTargetParams = {},
    config?: AxiosRequestConfig
  ): Promise<ListResponse<PatchTarget>> =>
    get(`${BASE}/patch_target/`, { params, ...config });

  const createPatchTarget = async (data: FormData | Partial<PatchTarget>): Promise<PatchTarget> =>
    post(
      `${BASE}/patch_target/`,
      data,
      data instanceof FormData ? { headers: { 'Content-Type': undefined } } : undefined,
    );

  const createPatchTargetBatch = async (data: Partial<PatchTarget>[]): Promise<PatchTarget[]> =>
    post(`${BASE}/patch_target/batch_create/`, { targets: data });

  const updatePatchTarget = async (id: number, data: FormData | Partial<PatchTarget>): Promise<PatchTarget> =>
    put(
      `${BASE}/patch_target/${id}/`,
      data,
      data instanceof FormData ? { headers: { 'Content-Type': undefined } } : undefined,
    );

  const deletePatchTarget = async (id: number): Promise<void> =>
    del(`${BASE}/patch_target/${id}/`);

  // 查询节点管理纳管节点（用于扫描/安装选择 node_mgmt 目标）
  const queryNodes = async (
    params: {
      page?: number;
      page_size?: number;
      name?: string;
    },
    config?: AxiosRequestConfig
  ): Promise<{ count: number; items: Array<{ id: string; name: string; ip: string; operating_system?: string }> }> => {
    const { page, page_size, name } = params;
    const qs = new URLSearchParams();
    if (page !== undefined) qs.append('page', String(page));
    if (page_size !== undefined) qs.append('page_size', String(page_size));
    const body = name ? { filters: { name: [{ value: name, lookup_expr: 'icontains' }] } } : {};
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return post(`/node_mgmt/api/node/search/${suffix}`, body, config);
  };

  // 目标机连通性探测(TCP 端口可达);同步执行,超时放宽到 20s
  const checkPatchTargetConnectivity = async (
    id: number,
    data?: FormData | Partial<PatchTarget>,
  ): Promise<{ target_id: number; connectivity_status: string; port: number; detail: string }> =>
    post(`${BASE}/patch_target/${id}/check_connectivity/`, data, {
      timeout: 20000,
      ...(data instanceof FormData ? { headers: { 'Content-Type': undefined } } : {}),
    });

  const testPatchTargetConnectivity = async (
    data: FormData | Partial<PatchTarget>,
  ): Promise<{ connectivity_status: string; port: number; detail: string }> =>
    post(`${BASE}/patch_target/test_connectivity/`, data, {
      timeout: 20000,
      ...(data instanceof FormData ? { headers: { 'Content-Type': undefined } } : {}),
    });

  // 已纳入节点列表（轻量：仅 node_id + name），不受分页限制
  const getImportedNodeIds = async (): Promise<{ items: Array<{ node_id: string; name: string }> }> =>
    get(`${BASE}/patch_target/imported-node-ids/`);

  // 查询节点管理云区域列表（用于手动录入选择云区域）
  const getCloudRegionList = async (
    params: { page?: number; page_size?: number; search?: string } = {}
  ): Promise<{ count: number; items: Array<{ id: number; name: string; display_name?: string }> }> =>
    get('/node_mgmt/api/cloud_region/', { params });

  // ── Dashboard ────────────────────────────────────────────────────────────────

  const getPatchDashboardStats = async (
    config?: AxiosRequestConfig
  ): Promise<PatchDashboardStats> =>
    get(`${BASE}/dashboard/stats/`, config);

  // ── 扫描设置 ───────────────────────────────────────────────────────────────────

  const getScanSetting = async (): Promise<ScanSetting> =>
    get(`${BASE}/scan_setting/`);

  const updateScanSetting = async (data: Partial<ScanSetting>): Promise<ScanSetting> =>
    put(`${BASE}/scan_setting/save/`, data);

  // ── 基线管理 ──────────────────────────────────────────────────────────────────

  const getBaselineList = async (
    params: { page?: number; page_size?: number; search?: string } = {},
    config?: AxiosRequestConfig
  ): Promise<ListResponse<any>> =>
    get(`${BASE}/baseline/`, { params, ...config });

  const getBaselineDetail = async (id: number): Promise<any> =>
    get(`${BASE}/baseline/${id}/`);

  const createBaseline = async (data: Record<string, any>): Promise<any> =>
    post(`${BASE}/baseline/`, data);

  const updateBaseline = async (id: number, data: Record<string, any>): Promise<any> =>
    put(`${BASE}/baseline/${id}/`, data);

  const deleteBaseline = async (id: number): Promise<void> =>
    del(`${BASE}/baseline/${id}/`);

  const getBaselineRequirements = async (id: number): Promise<any[]> =>
    get(`${BASE}/baseline/${id}/requirements/`);

  const addBaselineRequirements = async (id: number, data: { patch_ids: number[]; condition?: string }): Promise<any> =>
    post(`${BASE}/baseline/${id}/requirements/`, data);

  const removeBaselineRequirements = async (id: number, requirementIds: number[]): Promise<void> =>
    del(`${BASE}/baseline/${id}/requirements/`, { data: { requirement_ids: requirementIds } });

  const bindHostsToBaseline = async (id: number, targetIds: number[]): Promise<any> =>
    post(`${BASE}/baseline/${id}/bind_hosts/`, { target_ids: targetIds });

  const getBaselineHosts = async (id: number): Promise<any[]> =>
    get(`${BASE}/baseline/${id}/hosts/`);

  const assessBaseline = async (id: number): Promise<any> =>
    post(`${BASE}/baseline/${id}/assess/`);

  // ── 治理任务 ──────────────────────────────────────────────────────────────────

  const getGovernanceTaskList = async (
    params: { page?: number; page_size?: number; search?: string; task_type?: 'install' | 'reboot' } = {},
    config?: AxiosRequestConfig
  ): Promise<ListResponse<any>> =>
    get(`${BASE}/governance/`, { params, ...config });

  const getGovernanceTaskDetail = async (
    id: number,
    config?: AxiosRequestConfig,
  ): Promise<any> => get(`${BASE}/governance/${id}/`, config);

  const getGovernanceRiskItemDetail = async (
    taskId: number,
    riskItemId: string,
    config?: AxiosRequestConfig,
  ): Promise<any> =>
    get(`${BASE}/governance/${taskId}/risk-item-detail/`, {
      params: { risk_item_id: riskItemId },
      ...config,
    });

  const createGovernanceTask = async (data: Record<string, any>): Promise<any> =>
    post(`${BASE}/governance/`, data);

  const cancelGovernanceTask = async (id: number, reason: string): Promise<any> =>
    post(`${BASE}/governance/${id}/cancel/`, { reason });

  const retryGovernanceTaskHost = async (taskId: number, targetId: number): Promise<any> =>
    post(`${BASE}/governance/${taskId}/retry-host/`, { target_id: targetId });

  // ── 风险治理 ──────────────────────────────────────────────────────────────────

  const getRiskList = async (
    params: {
      view?: string;
      compliance?: string;
      remediation?: string;
      severity?: string;
      os_type?: string;
      host_id?: number;
      baseline_id?: number;
      patch_id?: number;
      search?: string;
      page?: number;
      page_size?: number;
    } = {},
    config?: AxiosRequestConfig
  ): Promise<any> =>
    get(`${BASE}/risk/`, { params, ...config });

  const getRiskSummary = async (config?: AxiosRequestConfig): Promise<any> =>
    get(`${BASE}/risk/summary/`, config);

  const remediateRisk = async (data: {
    items: Array<{ host_id: number; patch_id: number }>;
    execution_mode?: 'now' | 'window';
    execution_window_start?: string;
    execution_window_end?: string;
    auto_reboot?: boolean;
    name?: string;
  }): Promise<any> => post(`${BASE}/risk/remediate/`, data);

  const rebootRisk = async (data: {
    target_ids: number[];
    execution_window_start?: string;
    execution_window_end?: string;
    name?: string;
  }): Promise<any> => post(`${BASE}/risk/reboot/`, data);

  return {
    getPatchSourceList,
    testPatchSourceConnectivity,
    testExistingPatchSourceConnectivity,
    createPatchSource,
    updatePatchSource,
    deletePatchSource,
    setPatchSourceEnabled,
    checkPatchSourceConnectivity,
    syncPatchSource,
    previewSyncPatchSource,
    ingestPatchSource,
    getPatchList,
    getPatchDetail,
    createPatch,
    uploadWindowsPatchPackage,
    updatePatch,
    deletePatch,
    getPatchTargetList,
    createPatchTarget,
    createPatchTargetBatch,
    updatePatchTarget,
    deletePatchTarget,
    checkPatchTargetConnectivity,
    testPatchTargetConnectivity,
    getImportedNodeIds,
    getCloudRegionList,
    queryNodes,
    getPatchDashboardStats,
    // ── 扫描设置 ──
    getScanSetting,
    updateScanSetting,
    // ── 基线管理 ──
    getBaselineList,
    getBaselineDetail,
    createBaseline,
    updateBaseline,
    deleteBaseline,
    getBaselineRequirements,
    addBaselineRequirements,
    removeBaselineRequirements,
    bindHostsToBaseline,
    getBaselineHosts,
    assessBaseline,
    // ── 治理任务 ──
    getGovernanceTaskList,
    getGovernanceTaskDetail,
    getGovernanceRiskItemDetail,
    createGovernanceTask,
    cancelGovernanceTask,
    retryGovernanceTaskHost,
    // ── 风险治理 ──
    getRiskList,
    getRiskSummary,
    remediateRisk,
    rebootRisk,
  };
};

export default usePatchManagerApi;
