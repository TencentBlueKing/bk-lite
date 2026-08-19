/**
 * 策略 name 允许重名；展示层用次要上下文区分，不改库内 name。
 */

export interface PolicyNameSource {
  id?: string | number;
  name?: string;
  alert_name?: string;
  query_condition?: {
    type?: string;
    metric_name?: string;
    result_name?: string;
    expression?: string;
    queries?: Array<{ metric_name?: string }>;
    [key: string]: unknown;
  } | null;
  monitor_object_name?: string;
  monitor_object_display_name?: string;
  [key: string]: unknown;
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
