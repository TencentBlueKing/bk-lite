import {
  FormulaQueryCondition,
  MetricExpressionQueryCondition,
  MetricExpressionRow,
  MetricQueryCondition
} from './metricExpressionTypes';
import { FilterItem, MetricItem } from '@/app/monitor/types';
import { SourceFeild } from '@/app/monitor/types/event';
import { InstanceItem } from '@/app/monitor/types/search';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';

export type MetricExpressionMode = 'metric' | 'formula' | 'auto';

export const VARIABLE_SEQUENCE = 'abcdefghijklmnopqrstuvwxyz'.split('');
export const SUPPORTED_GROUP_ALGORITHMS = [
  'sum',
  'avg',
  'max',
  'min',
  'count'
];
const METRIC_NOT_READY_MESSAGE = '指标不存在或尚未加载';

type FormulaTokenType = 'identifier' | 'number' | 'operator' | 'leftParen' | 'rightParen';

interface FormulaToken {
  type: FormulaTokenType;
  value: string;
}

interface ParsedFormula {
  refs: string[];
  errors: string[];
}

export const getMetricRowRef = (index: number): string =>
  VARIABLE_SEQUENCE[index] || `m${index + 1}`;

export const shouldShowFormulaEditor = (
  mode: MetricExpressionMode
): boolean => mode === 'formula';

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

const tokenizeFormulaExpression = (expression: string): {
  tokens: FormulaToken[];
  errors: string[];
} => {
  const tokens: FormulaToken[] = [];
  const errors: string[] = [];
  let index = 0;

  while (index < expression.length) {
    const char = expression[index];

    if (/\s/.test(char)) {
      index += 1;
      continue;
    }

    if (/[0-9]/.test(char)) {
      let value = char;
      index += 1;
      while (index < expression.length && /[0-9.]/.test(expression[index])) {
        value += expression[index];
        index += 1;
      }
      if (!/^\d+(?:\.\d+)?$/.test(value)) {
        errors.push(`表达式包含非法数字：${value}`);
      }
      tokens.push({ type: 'number', value });
      continue;
    }

    if (/[a-zA-Z]/.test(char)) {
      let value = char;
      index += 1;
      while (index < expression.length && /[a-zA-Z0-9_]/.test(expression[index])) {
        value += expression[index];
        index += 1;
      }
      tokens.push({ type: 'identifier', value });
      continue;
    }

    if (['+', '-', '*', '/'].includes(char)) {
      tokens.push({ type: 'operator', value: char });
      index += 1;
      continue;
    }

    if (char === '(') {
      tokens.push({ type: 'leftParen', value: char });
      index += 1;
      continue;
    }

    if (char === ')') {
      tokens.push({ type: 'rightParen', value: char });
      index += 1;
      continue;
    }

    errors.push(`表达式包含非法字符：${char}`);
    index += 1;
  }

  return { tokens, errors };
};

const parseFormulaExpression = (expression: string): ParsedFormula => {
  const { tokens, errors } = tokenizeFormulaExpression(expression);
  const refs = new Set<string>();
  let index = 0;

  const current = () => tokens[index];
  const consume = () => {
    const token = tokens[index];
    index += 1;
    return token;
  };

  const parseFactor = (): boolean => {
    const token = current();

    if (!token) {
      errors.push('表达式语法不完整');
      return false;
    }

    if (token.type === 'identifier') {
      refs.add(token.value);
      consume();
      return true;
    }

    if (token.type === 'number') {
      consume();
      return true;
    }

    if (token.type === 'leftParen') {
      consume();
      if (!parseExpression()) {
        return false;
      }
      if (current()?.type !== 'rightParen') {
        errors.push('表达式括号不匹配');
        return false;
      }
      consume();
      return true;
    }

    if (token.type === 'rightParen') {
      errors.push('表达式括号不匹配');
      return false;
    }

    errors.push('表达式语法不完整');
    return false;
  };

  const parseTerm = (): boolean => {
    if (!parseFactor()) {
      return false;
    }

    while (current()?.type === 'operator' && ['*', '/'].includes(current().value)) {
      consume();
      if (!parseFactor()) {
        return false;
      }
    }

    return true;
  };

  const parseExpression = (): boolean => {
    if (!parseTerm()) {
      return false;
    }

    while (current()?.type === 'operator' && ['+', '-'].includes(current().value)) {
      consume();
      if (!parseTerm()) {
        return false;
      }
    }

    return true;
  };

  if (tokens.length && parseExpression() && current()) {
    errors.push(
      current()?.type === 'rightParen' ? '表达式括号不匹配' : '表达式语法不完整'
    );
  }

  return {
    refs: Array.from(refs),
    errors: Array.from(new Set(errors))
  };
};

const isPositiveInteger = (value: number | null): value is number =>
  Number.isInteger(value) && !!value && value > 0;

const validateMetricRows = (rows: MetricExpressionRow[]): string[] => {
  const errors: string[] = [];

  if (!rows.length) {
    errors.push('至少需要配置一个指标');
    return errors;
  }

  rows.forEach((row) => {
    if (!isPositiveInteger(row.metricId)) {
      errors.push(`指标 ${row.ref} 必须选择有效指标`);
    }

    if (!SUPPORTED_GROUP_ALGORITHMS.includes(row.groupAlgorithm)) {
      errors.push(`指标 ${row.ref} 缺少有效分组聚合方式`);
    }

    if (
      !Array.isArray(row.groupBy) ||
      !row.groupBy.length ||
      row.groupBy.some((item) => typeof item !== 'string' || !item.trim())
    ) {
      errors.push(`指标 ${row.ref} 缺少有效分组维度`);
    }

    row.filters.forEach((filter, index) => {
      if (!filter.name || !filter.method || !filter.value) {
        errors.push(`指标 ${row.ref} 的条件 ${index + 1} 未填写完整`);
      }
      if (index > 0 && !['and', 'or'].includes(filter.logic || '')) {
        errors.push(`指标 ${row.ref} 的条件 ${index + 1} 缺少 AND/OR 关系`);
      }
    });
  });

  return errors;
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

export const toMetricExpressionStateFromQueryCondition = (
  condition?: MetricExpressionQueryCondition,
  options: {
    groupAlgorithm?: string | null;
    groupBy?: string[];
  } = {}
): {
  rows: MetricExpressionRow[];
  resultName: string;
  expression: string;
} => {
  if (condition?.type === 'formula') {
    return {
      rows: condition.queries.map((query, index) =>
        createMetricRow(index, {
          ref: query.ref || getMetricRowRef(index),
          metricId: query.metric_id || null,
          filters: query.filter || [],
          groupAlgorithm: query.group_algorithm || 'avg',
          groupBy: query.group_by?.length ? query.group_by : ['instance_id']
        })
      ),
      resultName: condition.result_name || '',
      expression: condition.expression || 'a / b * 100'
    };
  }

  return {
    rows: toMetricRowsFromMetricCondition(
      condition?.type === 'metric' ? condition : undefined,
      options
    ),
    resultName: '',
    expression: 'a / b * 100'
  };
};

export const validateMetricExpressionPayload = ({
  resultName,
  expression,
  rows
}: {
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): string[] => {
  const normalizedRows = rows;
  const errors: string[] = [];

  errors.push(...validateMetricRows(normalizedRows));

  if (!resultName.trim()) {
    errors.push('结果名称不能为空');
  }

  if (!expression.trim()) {
    errors.push('表达式不能为空');
    return errors;
  }

  const parsedExpression = parseFormulaExpression(expression);
  errors.push(...parsedExpression.errors);

  const availableRefs = new Set(normalizedRows.map((row) => row.ref));
  const expressionRefs = new Set(parsedExpression.refs);
  const missingRefs = parsedExpression.refs.filter(
    (ref) => !availableRefs.has(ref)
  );

  if (expressionRefs.size < 2) {
    errors.push('表达式至少需要引用两个不同变量');
  }

  if (missingRefs.length) {
    errors.push(`表达式引用了不存在的变量：${missingRefs.join(', ')}`);
  }

  normalizedRows.forEach((row) => {
    if (!expressionRefs.has(row.ref)) {
      errors.push(`指标 ${row.ref} 未在表达式中使用`);
    }
  });

  return Array.from(new Set(errors));
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
    queries: rows.map((row) => ({
      ref: row.ref,
      metric_id: row.metricId,
      filter: row.filters,
      group_algorithm: row.groupAlgorithm,
      group_by: row.groupBy
    }))
  };
};

export const buildMetricExpressionQueryCondition = ({
  mode = 'auto',
  resultName,
  expression,
  rows
}: {
  mode?: MetricExpressionMode;
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
}): MetricExpressionQueryCondition => {
  const shouldBuildFormula =
    mode === 'formula' || (mode === 'auto' && rows.length > 1);

  if (shouldBuildFormula) {
    return buildFormulaQueryCondition({
      resultName,
      expression,
      rows
    });
  }

  const normalizedRows = assignMetricRowRefs(rows);

  const row = normalizedRows[0] || createMetricRow(0);
  const errors = validateMetricRows(normalizedRows);

  if (errors.length) {
    throw new Error(errors.join('；'));
  }

  return {
    type: 'metric',
    metric_id: row.metricId,
    filter: row.filters
  };
};

const escapeRegexValue = (value: unknown): string =>
  String(value ?? '').replace(/([\\^$.*+?()[\]{}|"])/g, '\\$1');

const findMetricForRow = (
  row: MetricExpressionRow,
  metrics: MetricItem[]
): MetricItem | undefined =>
  metrics.find(
    (item) => item.id === row.metricId || item.name === row.metricName
  );

const buildPreviewInstanceFilters = (
  metric: MetricItem,
  selectedInstance: Pick<InstanceItem, 'instance_id_values'>
): FilterItem[] => {
  const keys = metric.instance_id_keys || [];
  return keys.reduce<FilterItem[]>((filters, key, index) => {
    if (!key || index >= selectedInstance.instance_id_values.length) {
      return filters;
    }

    filters.push({
      name: key,
      method: '=~',
      value: escapeRegexValue(selectedInstance.instance_id_values[index])
    });
    return filters;
  }, []);
};

const appendFormulaPreviewInstanceFilters = (
  queryCondition: FormulaQueryCondition,
  rows: MetricExpressionRow[],
  metrics: MetricItem[],
  selectedInstance: Pick<InstanceItem, 'instance_id_values'>
): FormulaQueryCondition => ({
  ...queryCondition,
  queries: queryCondition.queries.map((query, index) => {
    const row = rows.find((item) => item.ref === query.ref) || rows[index];
    const metric = row ? findMetricForRow(row, metrics) : undefined;
    if (!metric) {
      throw new Error(METRIC_NOT_READY_MESSAGE);
    }

    return {
      ...query,
      filter: [
        ...(query.filter || []),
        ...buildPreviewInstanceFilters(metric, selectedInstance)
      ]
    };
  })
});

export const buildMetricExpressionPreviewPayload = ({
  monitorObjId,
  source,
  metrics,
  mode = 'auto',
  resultName,
  expression,
  rows,
  selectedInstance,
  period,
  periodUnit,
  algorithm,
  groupAlgorithm,
  groupBy,
  calculationUnit
}: {
  monitorObjId: string | number | null;
  source: SourceFeild;
  metrics: MetricItem[];
  mode?: MetricExpressionMode;
  resultName: string;
  expression: string;
  rows: MetricExpressionRow[];
  selectedInstance: Pick<
    InstanceItem,
    'instance_id' | 'instance_id_values'
  > | null;
  period: number | null;
  periodUnit: string;
  algorithm: string | null;
  groupAlgorithm: string | null;
  groupBy: string[];
  calculationUnit?: string | null;
}) => {
  if (!monitorObjId || !selectedInstance || !algorithm) {
    return null;
  }

  const queryCondition = buildMetricExpressionQueryCondition({
    mode,
    resultName,
    expression,
    rows
  });
  const anchorRow = rows[0] || createMetricRow(0);
  const anchorMetric = findMetricForRow(anchorRow, metrics);

  if (!anchorMetric) {
    throw new Error(METRIC_NOT_READY_MESSAGE);
  }

  const isFormula = queryCondition.type === 'formula';
  const previewQueryCondition = isFormula
    ? appendFormulaPreviewInstanceFilters(
      queryCondition,
      rows,
      metrics,
      selectedInstance
    )
    : queryCondition;
  const payloadGroupBy = isFormula
    ? sanitizeGroupBy(anchorRow.groupBy || [])
    : sanitizeGroupBy(groupBy);
  const payloadGroupAlgorithm = isFormula
    ? anchorRow.groupAlgorithm || 'avg'
    : groupAlgorithm || 'avg';

  return {
    monitor_object: monitorObjId,
    query_condition: previewQueryCondition,
    source,
    period: {
      type: periodUnit,
      value: period || 5
    },
    algorithm,
    group_algorithm: payloadGroupAlgorithm,
    group_by: payloadGroupBy,
    metric_unit: isFormula ? '' : anchorMetric.unit || '',
    calculation_unit: calculationUnit || '',
    preview: {
      instance_id: selectedInstance.instance_id,
      instance_id_values: selectedInstance.instance_id_values,
      duration_points: 30
    }
  };
};
