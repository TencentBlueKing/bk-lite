import useApiClient from '@/utils/request';
import { buildK8sResourceUrl, K8sResourceKind } from './model';

export const useK8sResourceApi = () => {
  const { get } = useApiClient();
  return {
    getOverview: (clusterId: string) => get(buildK8sResourceUrl('overview', clusterId)),
    getLayer: (clusterId: string, layer: 'namespace' | 'workload' | 'node', page: number, namespaceIds?: string[]) =>
      get(buildK8sResourceUrl('layer', clusterId, { layer, page, namespaceIds })),
    getWorkloadPods: (clusterId: string, workloadId: string, page = 1) =>
      get(buildK8sResourceUrl('workloadPods', clusterId, { workloadId, page })),
    getUnownedPods: (clusterId: string, page = 1) =>
      get(buildK8sResourceUrl('unownedPods', clusterId, { page })),
    getResources: (
      clusterId: string,
      kind: K8sResourceKind,
      options: { page?: number; pageSize?: number; search?: string; order?: string; namespaceId?: string; workloadId?: string; nodeId?: string }
    ) => get(buildK8sResourceUrl('resources', clusterId, {
      kind,
      page: options.page,
      pageSize: options.pageSize,
      search: options.search,
      order: options.order,
      namespaceId: options.namespaceId,
      workloadFilterId: options.workloadId,
      nodeId: options.nodeId,
    })),
  };
};
