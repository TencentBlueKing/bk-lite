import useApiClient from '@/utils/request';

export const useCustomCollectPluginApi = () => {
  const { get, post, put, del } = useApiClient();
  return {
    listPlugins: (params?: Record<string, unknown>) =>
      get('/cmdb/api/custom_collect_plugin/', { params }),
    getPlugin: (id: number | string) =>
      get(`/cmdb/api/custom_collect_plugin/${id}/`),
    createPlugin: (payload: Record<string, unknown>) =>
      post('/cmdb/api/custom_collect_plugin/', payload),
    updatePlugin: (id: number | string, payload: Record<string, unknown>) =>
      put(`/cmdb/api/custom_collect_plugin/${id}/`, payload),
    deletePlugin: (id: number | string) =>
      del(`/cmdb/api/custom_collect_plugin/${id}/`),
  };
};
