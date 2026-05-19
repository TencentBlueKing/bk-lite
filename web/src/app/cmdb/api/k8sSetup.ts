import useApiClient from '@/utils/request';

/**
 * CMDB k8s 引导式接入相关接口（对应后端 apps/cmdb/views/k8s_setup.py）
 */
export const useK8sSetupApi = () => {
  const { post } = useApiClient();

  // 生成安装 token
  const generateInstallToken = (params: {
    collector_cluster_id: string;
    cloud_region_id: number | string;
  }) => post('/cmdb/api/k8s_setup/install_token/', params);

  // 探测采集器是否已上报到 VictoriaMetrics
  const verifyCollectorReporting = (params: { collector_cluster_id: string }) =>
    post('/cmdb/api/k8s_setup/verify/', params);

  return {
    generateInstallToken,
    verifyCollectorReporting,
  };
};

/**
 * 给定 token，构造给用户复制的安装命令。
 * 注：open API 端点无需鉴权，由 kubectl 直接拉取 YAML。
 */
export const buildK8sInstallCommand = (token: string, originBase?: string): string => {
  const base = (originBase || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '');
  // OpenAPI 通过 Next.js 代理转发到后端 /api/v1/cmdb/open_api/k8s_setup/render/
  const url = `${base}/api/proxy/cmdb/open_api/k8s_setup/render/`;
  return `curl -s -X POST -H "Content-Type: application/json" \\\n  -d '{"token":"${token}"}' \\\n  ${url} | kubectl apply -f -`;
};
