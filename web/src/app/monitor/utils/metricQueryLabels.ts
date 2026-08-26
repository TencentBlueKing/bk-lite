/**
 * 指标公式中的实例标签占位符。对用户隐藏，保存/试算时再写回。
 */
export const METRIC_LABELS_PLACEHOLDER = '__$labels__';

const PROMQL_KEYWORDS = new Set(
  [
    'sum',
    'min',
    'max',
    'avg',
    'count',
    'rate',
    'irate',
    'increase',
    'delta',
    'idelta',
    'deriv',
    'predict_linear',
    'last_over_time',
    'avg_over_time',
    'min_over_time',
    'max_over_time',
    'sum_over_time',
    'count_over_time',
    'stddev_over_time',
    'stdvar_over_time',
    'quantile_over_time',
    'absent',
    'absent_over_time',
    'ceil',
    'floor',
    'round',
    'clamp',
    'clamp_min',
    'clamp_max',
    'abs',
    'sgn',
    'ln',
    'log2',
    'log10',
    'exp',
    'sqrt',
    'timestamp',
    'time',
    'vector',
    'scalar',
    'label_replace',
    'label_join',
    'histogram_quantile',
    'sort',
    'sort_desc',
    'topk',
    'bottomk',
    'by',
    'without',
    'on',
    'ignoring',
    'group_left',
    'group_right',
    'and',
    'or',
    'unless',
    'bool',
    'offset',
    'atan2',
    'nan',
    'inf'
  ].map((item) => item.toLowerCase())
);

const SELECTOR_RE = /\{([^{}]*)\}/g;
const CLAUSE_PROTECT_RE =
  /\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)/gi;

/** 编辑回显 / 界面展示：去掉 `__$labels__`，避免用户困惑。 */
export const stripMetricLabelsPlaceholder = (query = ''): string => {
  if (!query) return query;
  return query
    .replace(/,\s*__\$labels__/g, '')
    .replace(/__\$labels__\s*,\s*/g, '')
    .replace(/__\$labels__/g, '')
    .replace(/\{\s*,/g, '{')
    .replace(/,\s*\}/g, '}')
    .replace(/\{\s*\}/g, '');
};

const injectIntoSelectors = (query: string): string =>
  query.replace(/\{([^{}]*)\}/g, (_match, inner: string) => {
    if (inner.includes(METRIC_LABELS_PLACEHOLDER)) {
      return `{${inner}}`;
    }
    const trimmed = inner.trim();
    if (!trimmed) {
      return `{${METRIC_LABELS_PLACEHOLDER}}`;
    }
    return `{${trimmed},${METRIC_LABELS_PLACEHOLDER}}`;
  });

const collectProtectedRanges = (query: string): Array<[number, number]> => {
  const ranges: Array<[number, number]> = [];
  SELECTOR_RE.lastIndex = 0;
  let match = SELECTOR_RE.exec(query);
  while (match) {
    ranges.push([match.index, match.index + match[0].length]);
    match = SELECTOR_RE.exec(query);
  }
  CLAUSE_PROTECT_RE.lastIndex = 0;
  match = CLAUSE_PROTECT_RE.exec(query);
  while (match) {
    ranges.push([match.index, match.index + match[0].length]);
    match = CLAUSE_PROTECT_RE.exec(query);
  }
  return ranges;
};

const injectBareMetricNames = (query: string): string => {
  const protectedRanges = collectProtectedRanges(query);
  return query.replace(
    /\b([a-zA-Z_:][a-zA-Z0-9_:]*)\b(?!\s*[\({])/g,
    (match, name: string, offset: number) => {
      if (PROMQL_KEYWORDS.has(name.toLowerCase())) {
        return match;
      }
      if (
        protectedRanges.some(([start, end]) => offset >= start && offset < end)
      ) {
        return match;
      }
      return `${name}{${METRIC_LABELS_PLACEHOLDER}}`;
    }
  );
};

/**
 * 保存 / 试算 / 语法检查前：确保查询里带有 `__$labels__`。
 */
export const ensureMetricLabelsPlaceholder = (query = ''): string => {
  const trimmed = query.trim();
  if (!trimmed) return query;
  return injectBareMetricNames(injectIntoSelectors(trimmed));
};
