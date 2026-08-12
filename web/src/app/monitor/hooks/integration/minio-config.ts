interface MinioEditForm {
  metrics_api_version?: 'v2' | 'v3';
  scheme?: 'http' | 'https';
  auth_type?: 'public' | 'bearer';
  metric_extensions?: string[];
  insecure_skip_verify?: boolean;
}

type MinioMetricsVersion = 'v2' | 'v3';
type MinioAuthType = 'public' | 'bearer';

interface MinioPrometheusConfig {
  urls?: string[];
  namepass?: string[];
  namedrop?: string[];
  bearer_token_string?: string;
  insecure_skip_verify?: boolean;
  tags?: Record<string, unknown>;
}

interface MinioChildConfig {
  id?: string | number;
  env_config?: Record<string, string>;
  content?: { config?: MinioPrometheusConfig };
}

interface MinioPluginConfig {
  child?: MinioChildConfig;
}

const V3_CORE_PATHS = [
  'api/requests',
  'cluster/health',
  'cluster/erasure-set',
  'cluster/usage/objects',
  'system/cpu',
  'system/memory',
  'system/drive',
  'system/process',
  'system/network/internode'
];

const CORE_NAMEPASS = {
  v2: [
    'minio_cluster_capacity_*', 'minio_cluster_drive_*', 'minio_cluster_nodes_*',
    'minio_cluster_health_*', 'minio_s3_requests_*', 'minio_s3_traffic_*',
    'minio_node_cpu_*', 'minio_node_mem_*', 'minio_node_drive_*',
    'minio_node_process_*', 'minio_node_file_descriptor_*',
    'minio_inter_node_traffic_*'
  ],
  v3: [
    'minio_cluster_health_*', 'minio_cluster_erasure_set_*',
    'minio_cluster_usage_objects_*', 'minio_api_requests_*',
    'minio_system_cpu_*', 'minio_system_memory_*', 'minio_system_drive_*',
    'minio_system_process_*', 'minio_system_network_internode_*'
  ]
};

const EXTENSION_NAMEPASS: Record<string, string[]> = {
  bucket: ['minio_bucket_*', 'minio_cluster_usage_buckets_*'],
  replication: ['minio_*replication*'],
  lifecycle: ['minio_*ilm*', 'minio_*scanner*', 'minio_*heal*'],
  integrations: [
    'minio_audit_*', 'minio_cluster_audit_*', 'minio_cluster_notify_*',
    'minio_cluster_webhook_*', 'minio_notify_*', 'minio_notification_*',
    'minio_logger_webhook_*'
  ],
  security: ['minio_cluster_iam_*', 'minio_cluster_kms_*']
};

function isMetricsVersion(value: unknown): value is MinioMetricsVersion {
  return value === 'v2' || value === 'v3';
}

function isAuthType(value: unknown): value is MinioAuthType {
  return value === 'public' || value === 'bearer';
}

function inferExtensions(config: MinioPrometheusConfig, version: MinioMetricsVersion): string[] {
  const saved = config?.tags?.minio_metric_extensions;
  if (typeof saved === 'string') {
    return saved.split(',').map((item) => item.trim()).filter(Boolean);
  }
  const urls = config.urls?.filter((url): url is string => typeof url === 'string') ?? [];
  return version === 'v2' && urls.some((url) => url.includes('/v2/metrics/bucket'))
    ? ['bucket']
    : [];
}

export function getMinioEditCompatibilityValues(original: MinioPluginConfig): Pick<
  MinioEditForm,
  'metrics_api_version' | 'auth_type' | 'metric_extensions'
> {
  const config = original.child?.content?.config ?? {};
  const firstUrl = config.urls?.[0];
  const savedVersion = config.tags?.minio_metrics_version;
  const inferredVersion = typeof firstUrl === 'string' && firstUrl.includes('/metrics/v3/') ? 'v3' : 'v2';
  const version = isMetricsVersion(savedVersion) ? savedVersion : inferredVersion;
  const savedAuth = config.tags?.minio_auth_type;
  const auth = isAuthType(savedAuth) ? savedAuth : config.bearer_token_string ? 'bearer' : 'public';
  return {
    metrics_api_version: version,
    auth_type: auth,
    metric_extensions: inferExtensions(config, version)
  };
}

/** Rebuild every coupled MinIO field when an existing rendered config is edited. */
export function applyMinioEditConfig(
  result: MinioPluginConfig,
  original: MinioPluginConfig,
  form: MinioEditForm
): MinioPluginConfig {
  const originalConfig = original.child?.content?.config ?? {};
  const targetChild = result.child;
  const targetConfig = targetChild?.content?.config;
  const firstUrl = originalConfig.urls?.[0];
  if (!targetChild || !targetConfig || typeof firstUrl !== 'string') return result;

  let endpoint: URL;
  try {
    endpoint = new URL(firstUrl);
  } catch {
    return result;
  }
  const currentVersion = firstUrl.includes('/metrics/v3/') ? 'v3' : 'v2';
  const savedVersion = originalConfig.tags?.minio_metrics_version;
  const version = form.metrics_api_version ?? (isMetricsVersion(savedVersion) ? savedVersion : currentVersion);
  const scheme = form.scheme ?? (endpoint.protocol === 'https:' ? 'https' : 'http');
  const savedAuth = originalConfig.tags?.minio_auth_type;
  const auth = form.auth_type ?? (isAuthType(savedAuth)
    ? savedAuth
    : originalConfig.bearer_token_string ? 'bearer' : 'public');
  const extensions = form.metric_extensions ?? inferExtensions(originalConfig, version);
  const base = `${scheme}://${endpoint.host}`;

  if (version === 'v3') {
    targetConfig.urls = V3_CORE_PATHS.map((path) => `${base}/minio/metrics/v3/${path}`);
    if (extensions.includes('bucket')) targetConfig.urls.push(`${base}/minio/metrics/v3/cluster/usage/buckets`);
    if (extensions.includes('replication')) targetConfig.urls.push(`${base}/minio/metrics/v3/replication`);
    if (extensions.includes('lifecycle')) {
      targetConfig.urls.push(`${base}/minio/metrics/v3/ilm`, `${base}/minio/metrics/v3/scanner`);
    }
    if (extensions.includes('integrations')) {
      targetConfig.urls.push(
        `${base}/minio/metrics/v3/audit`,
        `${base}/minio/metrics/v3/notification`,
        `${base}/minio/metrics/v3/logger/webhook`
      );
    }
    if (extensions.includes('security')) targetConfig.urls.push(`${base}/minio/metrics/v3/cluster/iam`);
  } else {
    targetConfig.urls = [`${base}/minio/v2/metrics/cluster`];
    if (extensions.includes('bucket') || extensions.includes('replication')) {
      targetConfig.urls.push(`${base}/minio/v2/metrics/bucket`);
    }
    targetConfig.urls.push(`${base}/minio/v2/metrics/resource`);
  }

  targetConfig.namepass = [
    ...CORE_NAMEPASS[version],
    ...extensions.flatMap((extension) => EXTENSION_NAMEPASS[extension] || [])
  ];
  targetConfig.namedrop = ['*_ttfb_seconds_distribution*'];
  targetConfig.insecure_skip_verify = form.insecure_skip_verify ?? originalConfig.insecure_skip_verify ?? false;
  targetConfig.tags = {
    ...(targetConfig.tags || {}),
    minio_metrics_version: version,
    minio_auth_type: auth
  };
  if (extensions.length > 0) {
    targetConfig.tags.minio_metric_extensions = extensions.join(',');
  } else {
    delete targetConfig.tags.minio_metric_extensions;
  }

  const configId = String(targetChild.id || '').toUpperCase();
  const tokenKey = `BEARER_TOKEN__${configId}`;
  targetChild.env_config = { ...(targetChild.env_config || {}) };
  if (auth === 'bearer') {
    targetConfig.bearer_token_string = `\${${tokenKey}}`;
  } else {
    delete targetConfig.bearer_token_string;
    delete targetChild.env_config[tokenKey];
  }
  return result;
}
