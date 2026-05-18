import useApiClient from '@/utils/request';

export const useNodeMgmtSyncApi = () => {
  const { get, post, put } = useApiClient();

  const getNodeMgmtSyncTask = () =>
    get('/cmdb/api/node_mgmt_sync/task/');

  const updateNodeMgmtSyncTask = (params: any) =>
    put('/cmdb/api/node_mgmt_sync/task/', params);

  const getNodeMgmtSyncLatestRun = (params?: any) =>
    get('/cmdb/api/node_mgmt_sync/task/latest_run/', { params });

  const getNodeMgmtSyncDisplay = () =>
    get('/cmdb/api/node_mgmt_sync/task/display/');

  const runNodeMgmtSync = () =>
    post('/cmdb/api/node_mgmt_sync/task/run_sync/');

  const runNodeMgmtCollect = () =>
    post('/cmdb/api/node_mgmt_sync/task/run_collect/');

  return {
    getNodeMgmtSyncTask,
    updateNodeMgmtSyncTask,
    getNodeMgmtSyncLatestRun,
    getNodeMgmtSyncDisplay,
    runNodeMgmtSync,
    runNodeMgmtCollect,
  };
};
