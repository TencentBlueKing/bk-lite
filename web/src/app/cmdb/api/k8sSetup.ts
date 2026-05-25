import useApiClient from '@/utils/request';

/**
 * CMDB k8s 引导式接入相关接口（对应后端 apps/cmdb/views/k8s_setup.py）
 */
export const useK8sSetupApi = () => {
  const { post } = useApiClient();

  // 后端生成安装命令（URL 直连 Django open_api，不走 Next.js 代理）
  const generateInstallCommand = (params: {
    collector_cluster_id: string;
    cloud_region_id: number | string;
  }) => post('/cmdb/api/k8s_setup/install_command/', params);

  // 探测采集器是否已上报到 VictoriaMetrics
  const verifyCollectorReporting = (params: { collector_cluster_id: string }) =>
    post('/cmdb/api/k8s_setup/verify/', params);

  return {
    generateInstallCommand,
    verifyCollectorReporting,
  };
};
