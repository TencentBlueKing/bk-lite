import {
  FormulaQueryCondition,
  MetricExpressionQueryCondition,
  MetricExpressionRow,
  MetricQueryCondition
} from './metricExpressionTypes';

export const VARIABLE_SEQUENCE = 'abcdefghijklmnopqrstuvwxyz'.split('');

export const getMetricRowRef = (index: number): string =>
  VARIABLE_SEQUENCE[index] || `m${index + 1}`;

export const createMetricRow = (
  index: number,
  patch: Partial<MetricExpressionRow> = {}
): MetricExpressionRow => ({
  ref: getMetricRowRef(index),
  metricId: null,
  filters: [],
  groupAlgorithm: 'avg',
  groupBy: ['instance_id'],
  ...patch
});

export const assignMetricRowRefs = (
  rows: MetricExpressionRow[]
): MetricExpressionRow[] =>
  rows.map((row, index) => ({
    ...row,
    ref: getMetricRowRef(index)
  }));

export const extractFormulaRefs = (expression: string): string[] => {
  const refs = new Set<string>();
  const matcher = /\b[a-zA-Z][a-zA-Z0-9_]*\b/g;
  let match: RegExpExecArray | null;

  while ((match = matcher.exec(expression || ''))) {
    refs.add(match[0]);
  }

  return Array.from(refs);
};

export const toMetricRowsFromMetricCondition = (
  condition?: MetricQueryCondition,
  options: {
    groupAlgorithm?: string | null;
    groupBy?: string[];
  } = {}
): MetricExpressionRow[] => [
  createMetricRow(0, {
    metricId: condition?.metric_id || null,
    filters: condition?.filter || [],
    groupAlgorithm: options.groupAlgorithm || 'avg',
    groupBy: options.groupBy?.length ? options.groupBy : ['instance_id']
  })
];

export const validateMetricExpressionPayload = ({
  resultName,
  expression,
  rows
}: {
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): string[] => {
  const normalizedRows = assignMetricRowRefs(rows);
  const availableRefs = new Set(normalizedRows.map((row) => row.ref));
  const missingRefs = extractFormulaRefs(expression).filter(
    (ref) => !availableRefs.has(ref)
  );
  const errors: string[] = [];

  if (!resultName.trim()) {
    errors.push('结果名称不能为空');
  }

  if (!expression.trim()) {
    errors.push('表达式不能为空');
  }

  if (missingRefs.length) {
    errors.push(`表达式引用了不存在的变量：${missingRefs.join(', ')}`);
  }

  return errors;
};

export const buildFormulaQueryCondition = ({
  resultName,
  expression,
  rows
}: {
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): FormulaQueryCondition => {
  const errors = validateMetricExpressionPayload({
    resultName,
    expression,
    rows
  });

  if (errors.length) {
    throw new Error(errors.join('；'));
  }

  return {
    type: 'formula',
    result_name: resultName.trim(),
    expression: expression.trim(),
    queries: assignMetricRowRefs(rows).map((row) => ({
      ref: row.ref,
      metric_id: row.metricId as number,
      filter: row.filters,
      group_algorithm: row.groupAlgorithm,
      group_by: row.groupBy
    }))
  };
};

export const buildMetricExpressionQueryCondition = ({
  resultName,
  expression,
  rows
}: {
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): MetricExpressionQueryCondition => {
  const normalizedRows = assignMetricRowRefs(rows);

  if (normalizedRows.length <= 1) {
    const row = normalizedRows[0] || createMetricRow(0);
    return {
      type: 'metric',
      metric_id: row.metricId || undefined,
      filter: row.filters
    };
  }

  return buildFormulaQueryCondition({
    resultName,
    expression,
    rows: normalizedRows
  });
};
