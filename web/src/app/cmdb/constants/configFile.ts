/**
 * 实例详情「配置文件」Tab 开放的模型白名单。
 * 与网络配置文件采集目标模型保持一致：host + switch/router/firewall/loadbalance。
 */
export const CONFIG_FILE_SUPPORTED_MODEL_IDS = [
  'host',
  'switch',
  'router',
  'firewall',
  'loadbalance',
] as const;

export const NETWORK_CONFIG_FILE_MODEL_IDS = [
  'switch',
  'router',
  'firewall',
  'loadbalance',
] as const;

export const isConfigFileSupportedModel = (modelId?: string | null) => (
  !!modelId && (CONFIG_FILE_SUPPORTED_MODEL_IDS as readonly string[]).includes(modelId)
);

export const isNetworkConfigFileModel = (modelId?: string | null) => (
  !!modelId && (NETWORK_CONFIG_FILE_MODEL_IDS as readonly string[]).includes(modelId)
);
