import type { ConfigDiffItem, ConfigDiffReport } from '@/app/opspilot/types/global';

export const LIVE_YAML_ENDPOINT = '/opspilot/model_provider_mgmt/llm/fetch_k8s_deployment_yaml/';

interface LiveYamlRequest {
  kind: 'request';
  endpoint: typeof LIVE_YAML_ENDPOINT;
  payload: {
    namespace: string;
    name: string;
    cluster_name: string;
    skill_id: number;
  };
}

interface LiveYamlUnavailable {
  kind: 'unavailable';
  message: string;
}

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

export function buildLiveYamlRequest(
  report: ConfigDiffReport,
  item: ConfigDiffItem,
  t: Translate
): LiveYamlRequest | LiveYamlUnavailable | null {
  const skillId = report.skill_id ?? item.skill_id;
  if (!skillId) return null;

  const namespace = item.namespace.trim();
  if (!namespace || namespace === 'all') {
    return {
      kind: 'unavailable',
      message: t(
        'chat.liveYaml.allNamespaces',
        '该报告覆盖全部命名空间，无法定位唯一的 deployment 实时 YAML。'
      ),
    };
  }

  const name = item.workload_name.split(' ')[0]?.trim();
  if (!name) {
    return {
      kind: 'unavailable',
      message: t('chat.liveYaml.noName', '报告未提供可定位的 deployment 名称。'),
    };
  }

  return {
    kind: 'request',
    endpoint: LIVE_YAML_ENDPOINT,
    payload: {
      namespace,
      name,
      cluster_name: report.cluster_name,
      skill_id: skillId,
    },
  };
}
