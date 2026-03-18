import useApiClient from '@/utils/request';
import { AxiosRequestConfig } from 'axios';
import {
  DangerousRuleParams,
  DangerousRuleFormData,
  DangerousRuleListResponse,
  DangerousRule,
  EnabledDangerousPaths,
  TargetParams,
  TargetListResponse,
  Target,
  TargetFormData,
  ScriptParams,
  ScriptListResponse,
  Script,
  ScriptFormData,
  PlaybookParams,
  PlaybookListResponse,
  Playbook,
  PlaybookFormData,
  ScheduledTaskParams,
  ScheduledTaskListResponse,
  ScheduledTask,
  ScheduledTaskFormData,
  JobRecordParams,
  JobRecordListResponse,
  JobRecordDetail,
  ExecutionTargetSource,
  TargetListItem,
} from '@/app/job/types';

const useJobApi = () => {
  const { get, post, put, del, patch } = useApiClient();

  const getDangerousRuleList = async (
    params: DangerousRuleParams = {},
    config?: AxiosRequestConfig
  ): Promise<DangerousRuleListResponse> => {
    return await get('/job_mgmt/api/dangerous_rule/', {
      params,
      ...config,
    });
  };

  const getDangerousRuleDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<DangerousRule> => {
    return await get(`/job_mgmt/api/dangerous_rule/${id}/`, config);
  };

  const createDangerousRule = async (
    data: DangerousRuleFormData
  ): Promise<DangerousRule> => {
    return await post('/job_mgmt/api/dangerous_rule/', data);
  };

  const updateDangerousRule = async (
    id: number,
    data: Partial<DangerousRuleFormData>
  ): Promise<DangerousRule> => {
    return await put(`/job_mgmt/api/dangerous_rule/${id}/`, data);
  };

  const patchDangerousRule = async (
    id: number,
    data: Partial<DangerousRule>
  ): Promise<DangerousRule> => {
    return await patch(`/job_mgmt/api/dangerous_rule/${id}/`, data);
  };

  const deleteDangerousRule = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/dangerous_rule/${id}/`);
  };

  // Get enabled dangerous rules for script validation
  const getEnabledDangerousRules = async (
    config?: AxiosRequestConfig
  ): Promise<{ confirm: string[]; forbidden: string[] }> => {
    return await get('/job_mgmt/api/dangerous_rule/enabled_rules/', config);
  };

  // Dangerous path management
  const getDangerousPathList = async (
    params: DangerousRuleParams = {},
    config?: AxiosRequestConfig
  ): Promise<DangerousRuleListResponse> => {
    return await get('/job_mgmt/api/dangerous_path/', {
      params,
      ...config,
    });
  };

  const getDangerousPathDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<DangerousRule> => {
    return await get(`/job_mgmt/api/dangerous_path/${id}/`, config);
  };

  const createDangerousPath = async (
    data: DangerousRuleFormData
  ): Promise<DangerousRule> => {
    return await post('/job_mgmt/api/dangerous_path/', data);
  };

  const updateDangerousPath = async (
    id: number,
    data: Partial<DangerousRuleFormData>
  ): Promise<DangerousRule> => {
    return await put(`/job_mgmt/api/dangerous_path/${id}/`, data);
  };

  const patchDangerousPath = async (
    id: number,
    data: Partial<DangerousRule>
  ): Promise<DangerousRule> => {
    return await patch(`/job_mgmt/api/dangerous_path/${id}/`, data);
  };

  const deleteDangerousPath = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/dangerous_path/${id}/`);
  };

  // Get enabled dangerous paths for file distribution validation
  const getEnabledDangerousPaths = async (
    config?: AxiosRequestConfig
  ): Promise<EnabledDangerousPaths> => {
    return await get('/job_mgmt/api/dangerous_path/enabled_paths/', config);
  };

  // Target management
  const getTargetList = async (
    params: TargetParams = {},
    config?: AxiosRequestConfig
  ): Promise<TargetListResponse> => {
    return await get('/job_mgmt/api/target/', {
      params,
      ...config,
    });
  };

  const createTarget = async (
    data: FormData
  ): Promise<Target> => {
    return await post('/job_mgmt/api/target/', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const updateTarget = async (
    id: number,
    data: FormData
  ): Promise<Target> => {
    return await put(`/job_mgmt/api/target/${id}/`, data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const deleteTarget = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/target/${id}/`);
  };

  const syncTargets = async (data: { node_ids?: string[]; team: number[] }): Promise<void> => {
    return await post('/job_mgmt/api/target/sync_from_nodes/', data);
  };

  const testTargetConnection = async (
    data: Partial<TargetFormData>
  ): Promise<{ success: boolean; message?: string }> => {
    return await post('/job_mgmt/api/target/test_connection/', data);
  };

  // Query nodes from Node Manager
  const queryNodes = async (
    params: {
      cloud_region_id?: number;
      name?: string;
      ip?: string;
      os?: string;
      page?: number;
      page_size?: number;
    } = {},
    config?: AxiosRequestConfig
  ): Promise<{
    result: boolean;
    data: {
      count: number;
      items: Array<{
        id: string;
        name: string;
        ip: string;
        os_type: string;
        cloud_region: number;
        cloud_region_name: string;
      }>;
    };
  }> => {
    return await get('/job_mgmt/api/target/query_nodes/', {
      params,
      ...config,
    });
  };

  // Script management
  const getScriptList = async (
    params: ScriptParams = {},
    config?: AxiosRequestConfig
  ): Promise<ScriptListResponse> => {
    return await get('/job_mgmt/api/script/', {
      params,
      ...config,
    });
  };

  const getScriptDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<Script> => {
    return await get(`/job_mgmt/api/script/${id}/`, config);
  };

  const createScript = async (
    data: ScriptFormData
  ): Promise<Script> => {
    return await post('/job_mgmt/api/script/', data);
  };

  const updateScript = async (
    id: number,
    data: Partial<ScriptFormData>
  ): Promise<Script> => {
    return await put(`/job_mgmt/api/script/${id}/`, data);
  };

  const deleteScript = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/script/${id}/`);
  };

  // Playbook management
  const getPlaybookList = async (
    params: PlaybookParams = {},
    config?: AxiosRequestConfig
  ): Promise<PlaybookListResponse> => {
    return await get('/job_mgmt/api/playbook/', {
      params,
      ...config,
    });
  };

  const getPlaybookDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<Playbook> => {
    return await get(`/job_mgmt/api/playbook/${id}/`, config);
  };

  const createPlaybook = async (
    data: FormData
  ): Promise<Playbook> => {
    return await post('/job_mgmt/api/playbook/', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const updatePlaybook = async (
    id: number,
    data: Partial<PlaybookFormData>
  ): Promise<Playbook> => {
    return await patch(`/job_mgmt/api/playbook/${id}/`, data);
  };

  const deletePlaybook = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/playbook/${id}/`);
  };

  const upgradePlaybook = async (
    id: number,
    data: FormData
  ): Promise<Playbook> => {
    return await post(`/job_mgmt/api/playbook/${id}/upgrade/`, data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  const downloadPlaybook = async (id: number): Promise<Blob> => {
    return await get(`/job_mgmt/api/playbook/${id}/download/`, {
      responseType: 'blob',
    });
  };

  const batchDeletePlaybook = async (ids: number[]): Promise<{ deleted_count: number }> => {
    return await post('/job_mgmt/api/playbook/batch_delete/', { ids });
  };

  // File distribution - upload file first
  const uploadDistributionFile = async (
    file: File
  ): Promise<{ id: number; original_name: string; file_key: string; file_size: number; created_at: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    return await post('/job_mgmt/api/distribution_file/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  };

  // File distribution - execute distribution with file IDs
  const createFileDistribution = async (
    data: {
      name: string;
      file_ids: number[];
      target_source: ExecutionTargetSource;
      target_list: TargetListItem[];
      target_path: string;
      timeout?: number;
      overwrite_strategy?: string;
      team?: number[];
    }
  ): Promise<void> => {
    return await post('/job_mgmt/api/execution/file_distribution/', data);
  };

  // Scheduled Task management
  const getScheduledTaskList = async (
    params: ScheduledTaskParams = {},
    config?: AxiosRequestConfig
  ): Promise<ScheduledTaskListResponse> => {
    return await get('/job_mgmt/api/scheduled_task/', {
      params,
      ...config,
    });
  };

  const getScheduledTaskDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<ScheduledTask> => {
    return await get(`/job_mgmt/api/scheduled_task/${id}/`, config);
  };

  const createScheduledTask = async (
    data: ScheduledTaskFormData
  ): Promise<ScheduledTask> => {
    return await post('/job_mgmt/api/scheduled_task/', data);
  };

  const updateScheduledTask = async (
    id: number,
    data: Partial<ScheduledTaskFormData>
  ): Promise<ScheduledTask> => {
    return await put(`/job_mgmt/api/scheduled_task/${id}/`, data);
  };

  const patchScheduledTask = async (
    id: number,
    data: Partial<ScheduledTask>
  ): Promise<ScheduledTask> => {
    return await patch(`/job_mgmt/api/scheduled_task/${id}/`, data);
  };

  const deleteScheduledTask = async (id: number): Promise<void> => {
    return await del(`/job_mgmt/api/scheduled_task/${id}/`);
  };

  const runScheduledTaskNow = async (id: number): Promise<void> => {
    return await post(`/job_mgmt/api/scheduled_task/${id}/run_now/`);
  };

  interface TemplateParamItem {
    name: string;
    value: unknown;
    is_modified: boolean;
  }

  interface AdhocParamItem {
    value: string;
  }

  // Quick Execution
  const quickExecute = async (data: {
    name?: string;
    script_id?: number;
    script_type?: string;
    script_content?: string;
    target_source: ExecutionTargetSource;
    target_list: TargetListItem[];
    params?: TemplateParamItem[] | AdhocParamItem[];
    timeout?: number;
    team?: number[];
  }): Promise<any> => {
    return await post('/job_mgmt/api/execution/quick_execute/', data);
  };

  const playbookExecute = async (data: {
    name?: string;
    playbook_id: number;
    target_source: ExecutionTargetSource;
    target_list: TargetListItem[];
    params?: TemplateParamItem[];
    timeout?: number;
    team?: number[];
  }): Promise<any> => {
    return await post('/job_mgmt/api/execution/playbook_execute/', data);
  };

  // Job Record management
  const getJobRecordList = async (
    params: JobRecordParams = {},
    config?: AxiosRequestConfig
  ): Promise<JobRecordListResponse> => {
    return await get('/job_mgmt/api/execution/', {
      params,
      ...config,
    });
  };

  const getJobRecordDetail = async (
    id: number,
    config?: AxiosRequestConfig
  ): Promise<JobRecordDetail> => {
    return await get(`/job_mgmt/api/execution/${id}/`, config);
  };

  // Re-execute job
  const reExecuteJob = async (id: number): Promise<JobRecordDetail> => {
    return await post(`/job_mgmt/api/execution/${id}/re_execute/`);
  };

  const getCrontabPreview = async (
    cronExpression: string
  ): Promise<{ result: boolean; data: { next_runs: string[] } }> => {
    return await post('/job_mgmt/api/scheduled_task/crontab_preview/', {
      cron_expression: cronExpression,
    });
  };

  return {
    getDangerousRuleList,
    getDangerousRuleDetail,
    createDangerousRule,
    updateDangerousRule,
    patchDangerousRule,
    deleteDangerousRule,
    getEnabledDangerousRules,
    getDangerousPathList,
    getDangerousPathDetail,
    createDangerousPath,
    updateDangerousPath,
    patchDangerousPath,
    deleteDangerousPath,
    getEnabledDangerousPaths,
    getTargetList,
    createTarget,
    updateTarget,
    deleteTarget,
    syncTargets,
    testTargetConnection,
    queryNodes,
    getScriptList,
    getScriptDetail,
    createScript,
    updateScript,
    deleteScript,
    getPlaybookList,
    getPlaybookDetail,
    createPlaybook,
    updatePlaybook,
    deletePlaybook,
    upgradePlaybook,
    downloadPlaybook,
    batchDeletePlaybook,
    uploadDistributionFile,
    createFileDistribution,
    getScheduledTaskList,
    getScheduledTaskDetail,
    createScheduledTask,
    updateScheduledTask,
    patchScheduledTask,
    deleteScheduledTask,
    runScheduledTaskNow,
    getJobRecordList,
    getJobRecordDetail,
    reExecuteJob,
    getCrontabPreview,
    quickExecute,
    playbookExecute,
  };
};

export default useJobApi;
