import useApiClient from '@/utils/request';
import type {
  NodeMgmtSyncDisplayPayload,
  NodeMgmtSyncRun,
  NodeMgmtSyncTask,
} from '@/app/cmdb/types/autoDiscovery';

type NodeMgmtSyncTaskPatch = Partial<Pick<
  NodeMgmtSyncTask,
  'auto_sync_enabled' | 'auto_collect_enabled' | 'sync_interval_minutes' | 'collect_interval_minutes'
>>;

export const useNodeMgmtSyncApi = () => {
  const { get, post, put } = useApiClient();

  const getNodeMgmtSyncTask = () =>
    get<NodeMgmtSyncTask>('/cmdb/api/node_mgmt_sync/task/');

  const updateNodeMgmtSyncTask = (params: NodeMgmtSyncTaskPatch) =>
    put<NodeMgmtSyncTask>('/cmdb/api/node_mgmt_sync/task/', params);

  const getNodeMgmtSyncLatestRun = (params?: { run_type?: 'sync' | 'collect' }) =>
    get<NodeMgmtSyncRun>('/cmdb/api/node_mgmt_sync/task/latest_run/', { params });

  const getNodeMgmtSyncDisplay = () =>
    get<NodeMgmtSyncDisplayPayload>('/cmdb/api/node_mgmt_sync/task/display/');

  const runNodeMgmtSync = () =>
    post<NodeMgmtSyncRun>('/cmdb/api/node_mgmt_sync/task/run_sync/');

  const runNodeMgmtCollect = () =>
    post<NodeMgmtSyncRun>('/cmdb/api/node_mgmt_sync/task/run_collect/');

  return {
    getNodeMgmtSyncTask,
    updateNodeMgmtSyncTask,
    getNodeMgmtSyncLatestRun,
    getNodeMgmtSyncDisplay,
    runNodeMgmtSync,
    runNodeMgmtCollect,
  };
};
