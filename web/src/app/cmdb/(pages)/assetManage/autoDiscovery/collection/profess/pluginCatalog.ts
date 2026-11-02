import type { TaskStatusMap, TaskStatusStats, TreeNode } from '@/app/cmdb/types/autoDiscovery';

export const CATALOG_PREVIEW_COUNT = 6;
const PHYSICAL_SERVER_MODEL_ID = 'physcial_server';
export const DEFAULT_COLLECTION_ICON = '/assets/icons/cc-default_默认.svg';

export interface CatalogPluginTask {
  model_id?: string;
  driver_type?: string;
  params?: object | null;
}

const readCollectionProtocol = (params?: object | null) => {
  if (!params || !('collection_protocol' in params)) return undefined;
  const protocol = (params as { collection_protocol?: unknown }).collection_protocol;
  return typeof protocol === 'string' ? protocol : undefined;
};

const readCustomPluginPk = (params?: object | null) => {
  if (!params || !('custom_plugin_pk' in params)) return undefined;
  const raw = (params as { custom_plugin_pk?: unknown }).custom_plugin_pk;
  const pk = Number(raw);
  return Number.isInteger(pk) && pk > 0 ? pk : undefined;
};

export interface CatalogCategoryGroup {
  category: TreeNode;
  plugins: TreeNode[];
}

export interface CleanPluginNameResult {
  cleanName: string;
  isBeta: boolean;
}

export const cleanPluginName = (rawName?: string): CleanPluginNameResult => {
  if (!rawName) return { cleanName: '', isBeta: false };
  const isBeta = /【beta】|\[beta\]/i.test(rawName);
  const cleanName = rawName.replace(/【beta】|\[beta\]/gi, '').trim();
  return { cleanName, isBeta };
};

const COLLECTION_ICON_MAP: Array<{ keywords: string[]; src: string }> = [
  {
    keywords: ['k8s', 'kubernetes'],
    src: '/assets/icons/cc-k8s-cluster_K8S集群.svg',
  },
  {
    keywords: ['docker'],
    src: '/assets/icons/cc-docker_Docker.svg',
  },
  {
    keywords: ['vcenter', 'vmware', 'esxi'],
    src: '/assets/icons/cc-esxi-host_ESXi.svg',
  },
  {
    keywords: ['uis', 'h3c'],
    src: '/assets/icons/cc-h3c_cas_H3CCAS.svg',
  },
  {
    keywords: ['aliyun', 'ali', '阿里'],
    src: '/assets/icons/mm-aliyun_阿里云.svg',
  },
  {
    keywords: ['tencent', 'qcloud', '腾讯'],
    src: '/assets/icons/mm-tencentCloud_腾讯云.svg',
  },
  {
    keywords: ['oceanstor', '华为存储'],
    src: '/assets/icons/mm-oceanstor_oceanstor.svg',
  },
  {
    keywords: ['huawei', '华为', 'fusioninsight'],
    src: '/assets/icons/mm-huawei_华为.svg',
  },
  {
    keywords: ['unity', 'dell'],
    src: '/assets/icons/mm-unity_unity.svg',
  },
  {
    keywords: ['netapp'],
    src: '/assets/icons/mm-netapp_netapp.svg',
  },
  {
    keywords: ['storwize', 'ibm', 'symmetrix', 'emc', '存储', 'storage'],
    src: '/assets/icons/cc-storage_存储.svg',
  },
  {
    keywords: ['mssql', 'sql_server', 'sql server'],
    src: '/assets/icons/cc-sql-server_MSSQL.svg',
  },
  {
    keywords: ['mysql'],
    src: '/assets/icons/cc-mysql_MySQL.svg',
  },
  {
    keywords: ['postgresql', 'postgres', 'pgsql'],
    src: '/assets/icons/cc-postgresql_PostgreSQL.svg',
  },
  {
    keywords: ['redis'],
    src: '/assets/icons/cc-redis_REDIS.svg',
  },
  {
    keywords: ['mongodb', 'mongo'],
    src: '/assets/icons/cc-mongodb_MongoDB.svg',
  },
  {
    keywords: ['influxdb', 'influx'],
    src: '/assets/icons/cc-influxdb_InfluxDB.svg',
  },
  {
    keywords: ['dameng', '达梦'],
    src: '/assets/icons/mm-dameng_达梦.svg',
  },
  {
    keywords: ['oracle'],
    src: '/assets/icons/cc-oracle_Oracle.svg',
  },
  {
    keywords: ['tidb'],
    src: '/assets/icons/cc-tidb_TiDB.svg',
  },
  {
    keywords: ['minio'],
    src: '/assets/icons/cc-minio_Minio.svg',
  },
  {
    keywords: ['rabbitmq'],
    src: '/assets/icons/cc-rabbitmq_RabbitMQ.svg',
  },
  {
    keywords: ['kafka'],
    src: '/assets/icons/cc-kafka_Kafka.svg',
  },
  {
    keywords: ['tomcat'],
    src: '/assets/icons/cc-tomcat_Tomcat.svg',
  },
  {
    keywords: ['weblogic'],
    src: '/assets/icons/cc-weblogic_WebLogic.svg',
  },
  {
    keywords: ['websphere'],
    src: '/assets/icons/cc-websphere_websphere.svg',
  },
  {
    keywords: ['tongweb'],
    src: '/assets/icons/mm-tongweb_TongWeb.svg',
  },
  {
    keywords: ['jboss'],
    src: '/assets/icons/mm-jboss_JBoss.svg',
  },
  {
    keywords: ['ibmmq'],
    src: '/assets/icons/cc-ibmmq_IBMMQ.svg',
  },
  {
    keywords: ['nginx'],
    src: '/assets/icons/cc-nginx_Nginx.svg',
  },
  {
    keywords: ['ipmi'],
    src: '/assets/icons/mm-ipmi_ipmi.svg',
  },
  {
    keywords: ['redfish', '物理服务器'],
    src: '/assets/icons/cc-cloud-server_云服务器.svg',
  },
  {
    keywords: ['ssl', '证书', 'cert'],
    src: '/assets/icons/cc-certificate_证书.svg',
  },
  {
    keywords: ['配置', 'profile', 'config_file'],
    src: '/assets/icons/cc-profile_配置文件.svg',
  },
  {
    keywords: ['安全', 'firewall', '防火墙', 'waf', 'security'],
    src: '/assets/icons/cc-security-equipment_安全设备.svg',
  },
  {
    keywords: ['ip', '地址管理', 'subnet'],
    src: '/assets/icons/cc-ip_IP.svg',
  },
  {
    keywords: ['switch', '交换机', 'network'],
    src: '/assets/icons/cc-switch2_交换机.svg',
  },
  {
    keywords: ['router', '路由器'],
    src: '/assets/icons/cc-router_路由器.svg',
  },
  {
    keywords: ['windows', 'pc', 'winrm'],
    src: '/assets/icons/ll-winlogbeat_Windows事件日志.svg',
  },
  {
    keywords: ['cloud', 'zstack', 'openstack', 'smartx', 'winsphere', 'aws', 'azure'],
    src: '/assets/icons/cc-cloud-plat_云平台.svg',
  },
  {
    keywords: ['host', 'linux', 'hmc', '主机'],
    src: '/assets/icons/cc-host_主机.svg',
  },
];

export const getCollectionIconSrc = (tab: TreeNode) => {
  const searchText = [tab.model_id, tab.id, tab.name, tab.type, tab.task_type]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return (
    COLLECTION_ICON_MAP.find(({ keywords }) =>
      keywords.some((keyword) => searchText.includes(keyword)),
    )?.src || DEFAULT_COLLECTION_ICON
  );
};

export const getCategoryIconSrc = (category: TreeNode): string => {
  const text = [category.name, category.id, category.key]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (text.includes('容器') || text.includes('container') || text.includes('k8s')) {
    return '/assets/icons/cc-k8s-cluster_K8S集群.svg';
  }
  if (text.includes('数据') || text.includes('db') || text.includes('database')) {
    return '/assets/icons/cc-mysql_MySQL.svg';
  }
  if (text.includes('中间件') || text.includes('middleware')) {
    return '/assets/icons/cc-nginx_Nginx.svg';
  }
  if (text.includes('云') || text.includes('cloud')) {
    return '/assets/icons/cc-cloud-plat_云平台.svg';
  }
  if (text.includes('虚拟') || text.includes('virtual') || text.includes('vm')) {
    return '/assets/icons/cc-esxi-host_ESXi.svg';
  }
  if (text.includes('存储') || text.includes('storage')) {
    return '/assets/icons/cc-storage_存储.svg';
  }
  if (text.includes('网络') || text.includes('network') || text.includes('switch')) {
    return '/assets/icons/cc-switch2_交换机.svg';
  }
  if (text.includes('安全') || text.includes('security') || text.includes('firewall')) {
    return '/assets/icons/cc-security-equipment_安全设备.svg';
  }
  if (text.includes('证书') || text.includes('cert') || text.includes('ssl')) {
    return '/assets/icons/cc-certificate_证书.svg';
  }
  if (text.includes('ip') || text.includes('地址')) {
    return '/assets/icons/cc-ip_IP.svg';
  }
  return '/assets/icons/cc-host_主机.svg';
};

const normalizePhysicalServerProtocol = (value?: string | null) => {
  const protocol = String(value || 'ipmi').trim().toLowerCase();
  return protocol === 'redfish' ? 'redfish' : 'ipmi';
};

const RECONCILE_TASK_TYPES = new Set([
  'host',
  'db',
  'middleware',
  'protocol',
  'snmp',
  'other',
  'custom_script',
]);

/** 容器分组（K8s、Docker）不参与数据调和。 */
const RECONCILE_EXCLUDED_GROUP_IDS = new Set(['all', 'k8s']);

export const collectPlugins = (categories: TreeNode[]) =>
  categories
    .filter((category) => category.id !== 'all')
    .flatMap((category) => category.tabItems || []);

export const reconcilePluginGroups = (categories: TreeNode[]) =>
  categories
    .filter((category) => !RECONCILE_EXCLUDED_GROUP_IDS.has(category.id))
    .map((category) => ({
      id: category.id,
      name: category.name,
      plugins: (category.tabItems || []).filter(
        (plugin) =>
          RECONCILE_TASK_TYPES.has(plugin.task_type || '') &&
          !(
            plugin.task_type === 'custom_script' &&
            (plugin.model_id === 'vmware_vc' || plugin.id === 'vmware_vc')
          ),
      ),
    }))
    .filter((group) => group.plugins.length > 0);

export const findPluginCategory = (categories: TreeNode[], pluginId: string) =>
  categories.find(
    (category) =>
      category.id !== 'all' &&
      category.tabItems?.some((item) => item.id === pluginId),
  );

const pluginSearchText = (plugin: TreeNode) =>
  [plugin.name, plugin.desc, plugin.model_id, plugin.id, ...(plugin.tag || [])]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

export const filterCatalogCategories = (
  categories: TreeNode[],
  keyword: string,
): CatalogCategoryGroup[] => {
  const normalized = keyword.trim().toLowerCase();
  return categories
    .filter((category) => category.id !== 'all')
    .map((category) => ({
      category,
      plugins: (category.tabItems || []).filter(
        (plugin) => !normalized || pluginSearchText(plugin).includes(normalized),
      ),
    }))
    .filter((group) => group.plugins.length > 0);
};

export const getTaskStatusKey = (
  tab: Pick<TreeNode, 'id' | 'model_id' | 'type' | 'task_type' | 'custom_plugin_pk'>,
) => {
  if (tab.task_type === 'custom_script' && tab.custom_plugin_pk) {
    return `custom_script__${tab.custom_plugin_pk}`;
  }
  if (tab.model_id && tab.type) {
    if (tab.id === 'physcial_server_ipmi') {
      return `${tab.model_id}__${tab.type}__ipmi`;
    }
    if (tab.id === 'physcial_server_redfish') {
      return `${tab.model_id}__${tab.type}__redfish`;
    }
    return `${tab.model_id}__${tab.type}`;
  }
  return tab.model_id || tab.id;
};

export const getTaskStatusStats = (
  statusMap: TaskStatusMap,
  tab: Pick<TreeNode, 'id' | 'model_id' | 'type' | 'task_type' | 'custom_plugin_pk'>,
) => {
  const specificStats = statusMap[getTaskStatusKey(tab)];
  if (tab.task_type === 'custom_script') {
    return specificStats;
  }
  if (
    specificStats ||
    tab.id === 'physcial_server_ipmi' ||
    tab.id === 'physcial_server_redfish'
  ) {
    return specificStats;
  }
  return statusMap[tab.model_id || tab.id];
};

export const countPluginTasks = (
  stats?: (Partial<TaskStatusStats> & { partial_success?: number }) | null,
) => {
  if (!stats) return 0;
  if (typeof stats.total === 'number') return stats.total;
  return (
    (stats.running || 0) +
    (stats.success || 0) +
    (stats.failed || 0) +
    (stats.partial_success || 0) +
    (stats.not_start || 0)
  );
};

export const resolveCollectPlugin = (
  categories: TreeNode[],
  task: CatalogPluginTask,
) => {
  const plugins = collectPlugins(categories);
  const customPluginPk = readCustomPluginPk(task.params);
  if (customPluginPk) {
    const customPlugin = plugins.find(
      (plugin) =>
        plugin.task_type === 'custom_script' &&
        plugin.custom_plugin_pk === customPluginPk,
    );
    if (customPlugin) return customPlugin;
  }
  const modelId = task.model_id || '';
  const driverType = task.driver_type || '';

  if (modelId === PHYSICAL_SERVER_MODEL_ID && driverType === 'protocol') {
    const pluginId = `${PHYSICAL_SERVER_MODEL_ID}_${normalizePhysicalServerProtocol(
      readCollectionProtocol(task.params),
    )}`;
    const protocolPlugin = plugins.find((plugin) => plugin.id === pluginId);
    if (protocolPlugin) return protocolPlugin;
  }

  const sameModel = plugins.filter(
    (plugin) => plugin.model_id === modelId || plugin.id === modelId,
  );
  const typed = sameModel.find((plugin) => plugin.type && plugin.type === driverType);
  if (typed) return typed;
  if (sameModel.length === 1) return sameModel[0];
  return undefined;
};
