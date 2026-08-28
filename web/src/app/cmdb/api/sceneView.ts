import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { SceneViewRecord } from '@/app/cmdb/(pages)/views/scene/groupScenes';

export interface SceneViewPayload {
  name: string;
  model_ids: string[];
  tags: string[];
  tag_match?: 'and' | 'or';
  visibility?: 'personal' | 'organization' | 'global';
}

export interface SceneColumn {
  attr_id: string;
  attr_name: string;
  attr_type: string;
}

export interface SceneExecuteResult {
  total: number;
  models: Array<{
    model_id: string;
    count: number;
    insts: Array<Record<string, unknown>>;
    columns?: SceneColumn[];
  }>;
}

export interface SceneListResult {
  count: number;
  results: SceneViewRecord[];
  capabilities?: {
    can_org_share?: boolean;
    can_global?: boolean;
  };
}

export const useSceneViewApi = () => {
  const { get, post, put, del } = useApiClient();

  const listSceneViews = useCallback(
    () => get<SceneListResult>('/cmdb/api/scene_views/'),
    [get]
  );
  const getSceneView = useCallback(
    (id: number) => get<SceneViewRecord>(`/cmdb/api/scene_views/${id}/`),
    [get]
  );
  const createSceneView = useCallback(
    (data: SceneViewPayload) => post<SceneViewRecord>('/cmdb/api/scene_views/', data),
    [post]
  );
  const updateSceneView = useCallback(
    (id: number, data: SceneViewPayload) =>
      put<SceneViewRecord>(`/cmdb/api/scene_views/${id}/`, data),
    [put]
  );
  const deleteSceneView = useCallback(
    (id: number) => del(`/cmdb/api/scene_views/${id}/`),
    [del]
  );
  const executeSceneView = useCallback(
    (
      id: number,
      params?: {
        page?: number;
        page_size?: number;
        pagination?: Record<string, { page: number; page_size: number }>;
        searches?: Record<string, {
          field: string;
          type: string;
          value?: string | number | boolean | Array<string | number>;
          start?: string;
          end?: string;
          accurate?: boolean;
        }>;
      }
    ) => post<SceneExecuteResult>(`/cmdb/api/scene_views/${id}/execute/`, params || {}),
    [post]
  );
  const saveAsSceneView = useCallback(
    (id: number, name?: string) =>
      post<SceneViewRecord>(`/cmdb/api/scene_views/${id}/save_as/`, name ? { name } : {}),
    [post]
  );
  const exportSceneView = useCallback(
    (id: number) =>
      post<Blob>(`/cmdb/api/scene_views/${id}/export/`, {}, { responseType: 'blob' }),
    [post]
  );
  const getSceneTagOptions = useCallback(
    (modelIds: string[]) =>
      get<{ tags: string[] }>(
        `/cmdb/api/scene_views/tag_options/?model_ids=${encodeURIComponent(modelIds.join(','))}`
      ),
    [get]
  );

  return {
    listSceneViews,
    getSceneView,
    createSceneView,
    updateSceneView,
    deleteSceneView,
    executeSceneView,
    saveAsSceneView,
    exportSceneView,
    getSceneTagOptions,
  };
};
