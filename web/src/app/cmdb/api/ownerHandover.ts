import useApiClient from '@/utils/request';

export interface HandoverUser {
  id: number;
  username: string;
  display_name: string;
  label: string;
  disabled: boolean;
  employment_status: string;
}

export interface HandoverModel {
  model_id: string;
  model_name: string;
  fields: { attr_id: string; attr_name: string }[];
}

export interface HandoverChange {
  attr_id: string;
  attr_name: string;
  before: string;
  after: string;
}

export interface HandoverPreviewItem {
  model_id: string;
  model_name: string;
  inst_uuid: string;
  inst_name: string;
  organization: string;
  changes: HandoverChange[];
  transfer_status: 'pending' | 'succeeded' | 'failed';
}

export interface HandoverOutcomeStatus {
  inst_uuid: string;
  transfer_status: 'pending' | 'succeeded' | 'failed';
}

export interface HandoverPreview {
  preview_token: string;
  total: number;
  excluded_no_permission: number;
  inapplicable_models: { model_id: string; model_name: string }[];
  by_model: { model_id: string; model_name: string; count: number }[];
  items: HandoverPreviewItem[];
  page: number;
  page_size: number;
  from_user: HandoverUser;
  to_user: HandoverUser;
}

export interface HandoverTask {
  id: string;
  status: string;
  from_label: string;
  to_label: string;
  attr_name?: string;
  total_count: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
  message: string;
  created_at?: string;
}

export interface HandoverFailure {
  model_name: string;
  inst_name: string;
  reason_code: string;
  message: string;
}

export const useOwnerHandoverApi = () => {
  const { get, post } = useApiClient();
  const getModels = () => get('/cmdb/api/owner_handover/models/') as Promise<HandoverModel[]>;
  const searchUsers = (role: 'from' | 'to', search: string) =>
    get('/cmdb/api/owner_handover/users/', { params: { role, search } }) as Promise<HandoverUser[]>;
  const preview = (body: {
    from_user_id: number;
    to_user_id: number;
    attr_id: string;
    attr_name: string;
    model_ids?: string[];
    page?: number;
    page_size?: number;
  }) => post('/cmdb/api/owner_handover/preview/', body) as Promise<HandoverPreview>;
  const createTask = (previewToken: string, idempotencyKey: string) =>
    post('/cmdb/api/owner_handover/tasks/', { preview_token: previewToken }, {
      headers: { 'Idempotency-Key': idempotencyKey },
    }) as Promise<HandoverTask>;
  const getTask = (taskId: string) =>
    get(`/cmdb/api/owner_handover/tasks/${taskId}/`) as Promise<HandoverTask>;
  const listTasks = (userId?: number, page = 1, pageSize = 20) =>
    get('/cmdb/api/owner_handover/tasks/', {
      params: { user_id: userId || undefined, page, page_size: pageSize },
    }) as Promise<{ count: number; page: number; page_size: number; items: HandoverTask[] }>;
  const deleteTasks = (ids: string[]) =>
    post('/cmdb/api/owner_handover/tasks/delete/', { ids }) as Promise<{ deleted: number; kept: number }>;
  const getOutcomes = (taskId: string, instUuids: string[]) =>
    get(`/cmdb/api/owner_handover/tasks/${taskId}/outcomes/`, {
      params: { inst_uuid: instUuids.join(',') },
    }) as Promise<HandoverOutcomeStatus[]>;
  const getFailures = (taskId: string) =>
    get(`/cmdb/api/owner_handover/tasks/${taskId}/failures/`) as Promise<{
      count: number;
      items: HandoverFailure[];
    }>;
  const cancelTask = (taskId: string) =>
    post(`/cmdb/api/owner_handover/tasks/${taskId}/cancel/`) as Promise<HandoverTask>;
  const cleanupHistory = (userIds: number[], days: number) =>
    post('/cmdb/api/owner_handover/cleanup/', { user_id: userIds, days }) as Promise<{
      tasks: number;
      records: number;
      days: number;
    }>;
  return {
    getModels,
    searchUsers,
    preview,
    createTask,
    getTask,
    listTasks,
    deleteTasks,
    getOutcomes,
    getFailures,
    cancelTask,
    cleanupHistory,
  };
};
