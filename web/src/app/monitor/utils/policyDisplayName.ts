/**
 * 策略 name 允许重名；展示层用次要上下文区分，不改库内 name。
 */

export interface PolicyNameSource {
  id?: string | number;
  name?: string;
  alert_name?: string;
  query_condition?: {
    type?: string;
    metric_id?: string | number;
    metric_name?: string;
    result_name?: string;
    expression?: string;
    queries?: Array<{
      ref?: string;
      metric_id?: string | number;
      metric_name?: string;
    }>;
    [key: string]: unknown;
  } | null;
  monitor_object_name?: string;
  monitor_object_display_name?: string;
  [key: string]: unknown;
}

export interface PolicyMetricCatalogItem {
  id?: string | number;
  name?: string;
  display_name?: string;
}

/** 从策略配置提取用于区分同名的短上下文（指标优先；公式展开为指标名）。 */
export const getPolicyMetricContext = (policy?: PolicyNameSource | null): string => {
  if (!policy) return '';
  const query = policy.query_condition || {};
  if (query.type === 'formula') {
    const resultName = String(query.result_name || '').trim();
    let expression = String(query.expression || '').trim();
    const queries = Array.isArray(query.queries) ? query.queries : [];
    const refMap = new Map<string, string>();
    queries.forEach((item, index) => {
      if (!item || typeof item !== 'object') return;
      const rawRef = String(item.ref || '').trim() || String.fromCharCode(97 + index);
      const metricName = String(item.metric_name || '').trim() || rawRef;
      refMap.set(rawRef.toLowerCase(), metricName);
    });
    if (expression && refMap.size) {
      const pattern = new RegExp(
        `\\b(?:${Array.from(refMap.keys())
          .sort((a, b) => b.length - a.length)
          .map((ref) => ref.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
          .join('|')})\\b`,
        'gi'
      );
      expression = expression.replace(pattern, (match) => refMap.get(match.toLowerCase()) || match);
    }
    if (resultName && expression) return `${resultName}（${expression}）`;
    if (resultName || expression) return resultName || expression;
    const names = queries
      .map((item) => String(item?.metric_name || '').trim())
      .filter(Boolean);
    if (names.length) return names.join(' + ');
  }
  const metricName = String(query.metric_name || '').trim();
  if (metricName) return metricName;
  return '';
};

const metricCatalogLabel = (metric?: PolicyMetricCatalogItem | null): string =>
  String(metric?.display_name || metric?.name || '').trim();

const lookupCatalogMetric = (
  byId: Map<string, PolicyMetricCatalogItem>,
  byName: Map<string, PolicyMetricCatalogItem>,
  metricId?: string | number,
  metricName?: string
): PolicyMetricCatalogItem | undefined => {
  if (metricId !== undefined && metricId !== null && metricId !== '') {
    const hit = byId.get(String(metricId));
    if (hit) return hit;
  }
  const name = String(metricName || '').trim();
  if (name) return byName.get(name);
  return undefined;
};

/**
 * 策略指标列：目录 display_name 优先；有 metric_name/公式上下文时回落到 getPolicyMetricContext。
 * 不使用 alert_name。
 */
export const resolvePolicyMetricDisplayName = (
  policy?: PolicyNameSource | null,
  metrics: PolicyMetricCatalogItem[] = []
): string => {
  if (!policy) return '';
  const query = policy.query_condition || {};
  const byId = new Map<string, PolicyMetricCatalogItem>();
  const byName = new Map<string, PolicyMetricCatalogItem>();
  metrics.forEach((item) => {
    if (item.id !== undefined && item.id !== null && item.id !== '') {
      byId.set(String(item.id), item);
    }
    const name = String(item.name || '').trim();
    if (name) byName.set(name, item);
  });

  if (query.type === 'formula' && Array.isArray(query.queries)) {
    const enrichedQueries = query.queries.map((item) => {
      const label = metricCatalogLabel(
        lookupCatalogMetric(byId, byName, item?.metric_id, item?.metric_name)
      );
      return {
        ...item,
        metric_name: label || String(item?.metric_name || '').trim()
      };
    });
    const hasNamedMetric = enrichedQueries.some((item) =>
      Boolean(String(item.metric_name || '').trim())
    );
    if (!hasNamedMetric) return '';
    return getPolicyMetricContext({
      ...policy,
      query_condition: { ...query, queries: enrichedQueries }
    });
  }

  const catalogHit = lookupCatalogMetric(
    byId,
    byName,
    query.metric_id,
    query.metric_name
  );
  const catalogLabel = metricCatalogLabel(catalogHit);
  if (catalogLabel) return catalogLabel;
  return getPolicyMetricContext(policy);
};

export const getPolicySecondaryContext = (
  policy?: PolicyNameSource | null
): string => {
  if (!policy) return '';
  return (
    getPolicyMetricContext(policy) ||
    String(policy.monitor_object_display_name || policy.monitor_object_name || '').trim() ||
    (policy.id !== undefined && policy.id !== null && policy.id !== ''
      ? `ID ${policy.id}`
      : '')
  );
};

/** 当前结果集中同名时返回副文案，否则为空。 */
export const getPolicyNameDisambiguation = (
  policy: PolicyNameSource,
  siblings: PolicyNameSource[] = []
): string => {
  const name = String(policy.name || '').trim();
  if (!name) return getPolicySecondaryContext(policy);
  const sameNameCount = siblings.filter(
    (item) => String(item.name || '').trim() === name
  ).length;
  if (sameNameCount <= 1) return '';
  return getPolicySecondaryContext(policy);
};

export const formatPolicyDisplayName = (
  policy: PolicyNameSource,
  siblings: PolicyNameSource[] = []
): string => {
  const name = String(policy.name || '').trim() || '--';
  const secondary = getPolicyNameDisambiguation(policy, siblings);
  return secondary ? `${name}（${secondary}）` : name;
};
