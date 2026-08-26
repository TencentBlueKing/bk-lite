import useApiClient from '@/utils/request';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import { normalizeCanvasRefreshInterval } from '@/app/ops-analysis/utils/canvasRefreshInterval';

export interface CanvasDraftPayload {
  name?: string;
  desc?: string;
  view_sets: unknown;
  filters?: unknown;
  other?: unknown;
  refresh_interval?: number;
  base_url?: string;
}

export interface CanvasDraftHistoryItem {
  id: number;
  label: string;
  created_at: string;
  yaml: string;
}

/** 恢复检查点时同步内存中的周期刷新间隔（与进编辑从正式画布加载一致）。 */
export const restoreDraftRefreshInterval = (
  payload: CanvasDraftPayload,
  setSavedRefreshInterval: (interval: number) => void,
) => {
  setSavedRefreshInterval(
    normalizeCanvasRefreshInterval(payload.refresh_interval ?? 0),
  );
};

export const toCanvasDraftResourceId = (dataId?: string | number) => {
  const id = Number(dataId);
  return Number.isFinite(id) && id > 0 ? id : undefined;
};

const draftPath = (resourceType: CanvasType, resourceId: number) =>
  `/operation_analysis/api/canvas_draft/${resourceType}/${resourceId}/`;

export const useCanvasDraftApi = () => {
  const { get, post, patch } = useApiClient();

  const saveCheckpoint = (
    resourceType: CanvasType,
    resourceId: number,
    payload: CanvasDraftPayload,
  ) =>
    post<{ id: number; payload: CanvasDraftPayload }>(
      `${draftPath(resourceType, resourceId)}checkpoints/`,
      { payload },
      { suppressErrorNotification: true },
    );

  const listHistory = (resourceType: CanvasType, resourceId: number) =>
    get<CanvasDraftHistoryItem[]>(`${draftPath(resourceType, resourceId)}history/`);

  const restoreCheckpoint = (
    resourceType: CanvasType,
    resourceId: number,
    checkpointId: number,
  ) =>
    post<{ id: number; payload: CanvasDraftPayload }>(
      `${draftPath(resourceType, resourceId)}restore/`,
      { checkpoint_id: checkpointId },
      { suppressErrorNotification: true },
    );

  const updateCheckpointLabel = (
    resourceType: CanvasType,
    resourceId: number,
    checkpointId: number,
    label: string,
  ) =>
    patch<{ id: number; label: string }>(
      `${draftPath(resourceType, resourceId)}checkpoints/${checkpointId}/`,
      { label },
      { suppressErrorNotification: true },
    );

  return {
    saveCheckpoint,
    listHistory,
    restoreCheckpoint,
    updateCheckpointLabel,
  };
};
