import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export interface CmdbMonitorTaskItem {
  id: string;
  inst_uuid: string;
  model_id: string;
  object_name: string;
  inst_name: string;
  ip: string;
  status: string;
  monitor_id: string;
}

export interface CmdbMonitorTaskDraft {
  id: string;
  object_name: string;
  row_count: number;
}

export interface CmdbMonitorTask {
  id: string;
  status: string;
  operator?: string;
  summary?: Record<string, number>;
  retain_until?: string | null;
  created_at?: string | null;
  items?: CmdbMonitorTaskItem[];
  drafts?: CmdbMonitorTaskDraft[];
}

export interface CmdbAccessDraft {
  id: string;
  object_name: string;
  task_id: string;
  expires_at?: string | null;
  rows?: Array<Record<string, unknown>>;
}

export const useModuleLinkApi = () => {
  const { get, post } = useApiClient();

  const createCmdbMonitorTask = useCallback(
    (instUuids: string[]) =>
      post('/module_link/api/cmdb_monitor_tasks/', { inst_uuids: instUuids }),
    [post],
  );

  const getCmdbMonitorTask = useCallback(
    (taskId: string) => get(`/module_link/api/cmdb_monitor_tasks/${taskId}/`),
    [get],
  );

  const cancelCmdbMonitorTask = useCallback(
    (taskId: string) => post(`/module_link/api/cmdb_monitor_tasks/${taskId}/cancel/`),
    [post],
  );

  const assignCmdbMonitorObject = useCallback(
    (
      taskId: string,
      payload: { item_ids: string[]; object_name: string; remember?: boolean },
    ) => post(`/module_link/api/cmdb_monitor_tasks/${taskId}/assign_object/`, payload),
    [post],
  );

  const getAccessDraft = useCallback(
    (draftId: string) => get(`/module_link/api/access_drafts/${draftId}/`),
    [get],
  );

  return {
    createCmdbMonitorTask,
    getCmdbMonitorTask,
    cancelCmdbMonitorTask,
    assignCmdbMonitorObject,
    getAccessDraft,
  };
};
