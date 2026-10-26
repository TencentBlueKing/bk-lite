import {
  FormulaQueryCondition,
  MetricExpressionQueryCondition,
  MetricExpressionRow,
  MetricQueryCondition,
  MultiQueryCondition,
  MultiThresholdField
} from './metricExpressionTypes';
import { MetricItem, ThresholdField } from '@/app/monitor/types';
import { SourceFeild } from '@/app/monitor/types/event';
import { InstanceItem } from '@/app/monitor/types/search';
import { sanitizeGroupBy } from '@/app/monitor/utils/metricDimensions';
import { isStringArray } from '@/app/monitor/utils/common';

export type MetricExpressionMode = 'metric' | 'formula' | 'multi' | 'auto';
export type MetricExpressionQueryType = 'metric' | 'formula' | 'multi';

export const DEFAULT_MULTI_LEVEL_THRESHOLD: MultiThresholdField[] = [
  { level: 'critical', method: '>', value: null },
  { level: 'error', method: '>', value: null },
  { level: 'warning', method: '>', value: null }
];
export const DEFAULT_FORMULA_RESULT_NAME = '计算指标';
export const DEFAULT_FORMULA_EXPRESSION = 'a / b * 100';
export const VARIABLE_SEQUENCE = 'abcdefghijklmnopqrstuvwxyz'.split('');
export const SUPPORTED_GROUP_ALGORITHMS = [
  'sum',
  'avg',
  'max',
  'min',
  'count'
];
const METRIC_NOT_READY_MESSAGE = '指标不存在或尚未加载';
const LABEL_NAME_PATTERN = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

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

export const getMetricExpressionModeForRows = (
  _rows: MetricExpressionRow[],
  explicitMode?: string | null
): MetricExpressionMode => {
  if (
    explicitMode === 'formula' ||
    explicitMode === 'multi' ||
    explicitMode === 'metric'
  ) {
    return explicitMode;
  }
  return 'metric';
};

export const resolveMetricExpressionUnits = ({
  queryType,
  metricUnit,
  calculationUnit,
  thresholdUnit
}: {
  queryType: MetricExpressionQueryType;
  metricUnit: string | null | undefined;
  calculationUnit: string | null | undefined;
  thresholdUnit: string | null | undefined;
}): { metricUnit: string; calculationUnit: string; thresholdUnit: string } => {
  // none/short 与后端批量创建一致：不作为可配置 metric_unit，避免 serializer
  // get_effective_units 提升后被 is_known_unit 拒绝（「结果单位无效」）。
  const normalizedMetricUnit =
    !metricUnit ||
    metricUnit === 'none' ||
    metricUnit === 'short' ||
    queryType === 'formula' ||
    isStringArray(metricUnit)
      ? ''
      : metricUnit;
  return {
    metricUnit: normalizedMetricUnit,
    calculationUnit: calculationUnit || '',
    thresholdUnit: thresholdUnit || calculationUnit || ''
  };
};

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

export type ConditionCount = 'single' | 'multi';
export type ConditionSource = 'metric' | 'formula';

/** 条数 × 来源派生保存类型。多条件在放开条件内公式前仍是 multi。 */
export const derivedQueryType = (
  count: ConditionCount,
  source: ConditionSource
): MetricExpressionQueryType => (count === 'multi' ? 'multi' : source);

export const conditionLayersFromQueryType = (
  queryType: string | null | undefined
): { count: ConditionCount; source: ConditionSource } => {
  if (queryType === 'multi') {
    return { count: 'multi', source: 'metric' };
  }
  if (queryType === 'formula') {
    return { count: 'single', source: 'formula' };
  }
  return { count: 'single', source: 'metric' };
};

/** 多条件内切换来源不改变派生类型，因此不提示。 */
export const shouldWarnQueryTypeChange = ({
  isPersisted,
  savedType,
  nextType
}: {
  isPersisted: boolean;
  savedType: string | null | undefined;
  nextType: string;
}): boolean => Boolean(isPersisted && savedType && savedType !== nextType);

/** 单条件与多条件卡都渲染来源开关。多条件内切换来源不改变派生类型。 */
export const shouldShowConditionSourceSwitch = (
  count: ConditionCount
): boolean => count === 'single' || count === 'multi';

const FORMULA_PER_SERIES_ALGORITHMS = new Set(['rate', 'changes', 'deriv']);

export const isFormulaConditionRow = (row: MetricExpressionRow): boolean =>
  row.source === 'formula';

export const switchConditionSource = (
  row: MetricExpressionRow,
  source: ConditionSource
): MetricExpressionRow => {
  if ((row.source || 'metric') === source) {
    return row;
  }
  if (source === 'formula') {
    const first = createMetricRow(0, {
      ref: `${row.ref}1`,
      metricId: row.metricId,
      ...(row.metricName ? { metricName: row.metricName } : {}),
      ...(row.metricLabel ? { metricLabel: row.metricLabel } : {}),
      filters: row.filters,
      groupAlgorithm: row.groupAlgorithm || 'sum',
      groupBy: row.groupBy
    });
    const second = createMetricRow(1, {
      ref: `${row.ref}2`,
      groupAlgorithm: row.groupAlgorithm || 'sum',
      groupBy: row.groupBy
    });
    const operands = row.operands && row.operands.length >= 2 ? row.operands : [first, second];
    return {
      ...row,
      source: 'formula',
      metricId: null,
      metricName: undefined,
      metricLabel: undefined,
      filters: [],
      resultName: row.resultName || row.metricLabel || '',
      expression: row.expression || `${operands[0].ref} / ${operands[1].ref} * 100`,
      operands: operands.map((operand) => ({ ...operand, groupBy: row.groupBy })),
      metricUnit: '',
      algorithm: FORMULA_PER_SERIES_ALGORITHMS.has(row.algorithm || '')
        ? 'avg_over_time'
        : row.algorithm
    };
  }
  const first = row.operands?.[0];
  return {
    ...row,
    source: 'metric',
    metricId: first?.metricId ?? null,
    ...(first?.metricName ? { metricName: first.metricName } : { metricName: undefined }),
    ...(first?.metricLabel ? { metricLabel: first.metricLabel } : { metricLabel: undefined }),
    filters: first?.filters || [],
    groupAlgorithm: first?.groupAlgorithm || row.groupAlgorithm || 'avg',
    expression: undefined,
    operands: undefined,
    resultName: undefined
  };
};

/** 单条件从原生切到计算：保留第一行指标，补一个空操作数，变量回到 a、b。 */
export const rowsAfterEnteringFormula = (
  rows: MetricExpressionRow[]
): MetricExpressionRow[] => {
  const primary = rows[0] ?? createMetricRow(0);
  const second = createMetricRow(1, {
    groupBy: primary.groupBy?.length ? primary.groupBy : ['instance_id'],
    groupAlgorithm: primary.groupAlgorithm || 'sum'
  });
  return assignMetricRowRefs([
    {
      ...primary,
      source: undefined,
      operands: undefined,
      expression: undefined,
      resultName: undefined,
      role: undefined,
      threshold: undefined
    },
    second
  ]);
};

export const rowsAfterEnteringMulti = (
  rows: MetricExpressionRow[],
  defaults: { algorithm: string; groupBy: string[] }
): MetricExpressionRow[] => {
  const seeded = rows.map((row) => ({
    ...row,
    role: row.role || ('level' as const),
    algorithm: row.algorithm || defaults.algorithm || 'avg_over_time',
    threshold:
      row.threshold ||
      DEFAULT_MULTI_LEVEL_THRESHOLD.map((item) => ({ ...item }))
  }));
  if (seeded.length >= 2) {
    return seeded;
  }
  return [
    ...seeded,
    createMetricRow(seeded.length, {
      role: 'level',
      algorithm: defaults.algorithm || 'avg_over_time',
      groupBy: defaults.groupBy.length ? defaults.groupBy : ['instance_id'],
      threshold: DEFAULT_MULTI_LEVEL_THRESHOLD.map((item) => ({ ...item }))
    })
  ];
};

export const rowsAfterLeavingMulti = (
  rows: MetricExpressionRow[]
): MetricExpressionRow[] => (rows.length ? rows.slice(0, 1) : [createMetricRow(0)]);

/** 后续条件选指标时只保留锚点已有维度；没有交集时沿用锚点。 */
export const groupByAfterSelectingMetric = (
  availableGroupBy: string[],
  anchorGroupBy: string[],
  constrainToAnchor: boolean
): string[] => {
  const next = constrainToAnchor
    ? availableGroupBy.filter((item) => anchorGroupBy.includes(item))
    : availableGroupBy;
  return next.length ? next : anchorGroupBy;
};

export const alignFollowerGroupBy = (
  rows: MetricExpressionRow[],
  anchorGroupBy: string[]
): MetricExpressionRow[] =>
  rows.map((row, index) => {
    const groupBy =
      index === 0
        ? anchorGroupBy
        : row.groupBy.filter((item) => anchorGroupBy.includes(item));
    if (row.source !== 'formula') {
      return { ...row, groupBy };
    }
    const allowed = groupBy.length ? groupBy : anchorGroupBy;
    const operands = (row.operands || []).map((operand, operandIndex) => {
      if (index === 0 && operandIndex === 0) {
        return { ...operand, groupBy: anchorGroupBy };
      }
      const kept = (operand.groupBy || []).filter((item) => allowed.includes(item));
      return { ...operand, groupBy: kept.length ? kept : allowed };
    });
    return {
      ...row,
      groupBy: operands[0]?.groupBy?.length ? operands[0].groupBy : allowed,
      operands
    };
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

const isScalarFilterValue = (value: unknown): value is string | number | boolean =>
  ['string', 'number', 'boolean'].includes(typeof value);

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
    } else {
      row.groupBy.forEach((item) => {
        if (!LABEL_NAME_PATTERN.test(item)) {
          errors.push(`指标 ${row.ref} 分组维度 ${item} 包含非法字符`);
        }
      });
    }

    row.filters.forEach((filter, index) => {
      if (
        !filter.name ||
        !filter.method ||
        filter.value === undefined ||
        filter.value === null
      ) {
        errors.push(`指标 ${row.ref} 的条件 ${index + 1} 未填写完整`);
      }
      if (index > 0 && filter.logic && !['and', 'or'].includes(filter.logic)) {
        errors.push(`指标 ${row.ref} 的条件 ${index + 1} 缺少 AND/OR 关系`);
      }
      if (
        filter.value !== undefined &&
        filter.value !== null &&
        !isScalarFilterValue(filter.value)
      ) {
        errors.push(`指标 ${row.ref} 的条件 ${index + 1} 的值必须是字符串、数字或布尔值`);
      }
    });
  });

  return errors;
};

const storedMetricName = (metricName?: string | null) =>
  String(metricName || '').trim();

/** 目录里按 id 命中；id 不在当前插件目录时，再按指标名命中同名行。 */
export const findCatalogMetric = (
  metrics: MetricItem[],
  metricId?: number | null,
  metricName?: string | null
): MetricItem | undefined => {
  if (metricId != null && metricId !== 0) {
    const byId = metrics.find((item) => String(item.id) === String(metricId));
    if (byId) return byId;
  }
  const name = storedMetricName(metricName);
  if (!name) return undefined;
  return metrics.find((item) => item.name === name);
};

/**
 * 编辑回填用的指标身份。
 * 当前目录有同名指标时改用目录里的 id，这样下拉 value（指标名）能对上选项。
 * 只有名称时仍返回名称，避免下拉停在空白。
 */
export const resolveHydratedMetricFields = (
  metrics: MetricItem[],
  metricId?: number | null,
  metricName?: string | null
): { metricId: number | null; metricName?: string } => {
  const name = storedMetricName(metricName);
  const catalog = findCatalogMetric(metrics, metricId, name);
  if (catalog) {
    return { metricId: catalog.id, metricName: catalog.name };
  }
  const storedId = metricId != null && metricId !== 0 ? Number(metricId) : null;
  return {
    metricId: storedId != null && Number.isFinite(storedId) ? storedId : null,
    ...(name ? { metricName: name } : {})
  };
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
    ...(storedMetricName(condition?.metric_name)
      ? { metricName: storedMetricName(condition?.metric_name) }
      : {}),
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
  if (condition?.type === 'multi') {
    return {
      rows: condition.queries.map((query, index) => {
        const groupBy = query.group_by?.length ? query.group_by : ['instance_id'];
        if (query.source === 'formula') {
          return createMetricRow(index, {
            ref: query.ref || getMetricRowRef(index),
            source: 'formula',
            metricId: null,
            resultName: storedMetricName(query.metric_name),
            expression: query.expression || '',
            groupBy,
            algorithm: query.algorithm,
            metricUnit: '',
            calculationUnit: query.calculation_unit,
            thresholdUnit: query.threshold_unit,
            role: query.role,
            threshold: query.threshold,
            ...(query.count_predicate ? { countPredicate: query.count_predicate } : {}),
            operands: (query.operands || []).map((operand, operandIndex) =>
              createMetricRow(operandIndex, {
                ref: operand.ref || `${query.ref || 'a'}${operandIndex + 1}`,
                metricId: operand.metric_id || null,
                ...(storedMetricName(operand.metric_name)
                  ? { metricName: storedMetricName(operand.metric_name) }
                  : {}),
                filters: operand.filter || [],
                groupAlgorithm: operand.group_algorithm || 'sum',
                groupBy: operand.group_by?.length ? operand.group_by : groupBy
              })
            )
          });
        }
        return createMetricRow(index, {
          ref: query.ref || getMetricRowRef(index),
          metricId: query.metric_id || null,
          ...(storedMetricName(query.metric_name)
            ? { metricName: storedMetricName(query.metric_name) }
            : {}),
          filters: query.filter || [],
          groupAlgorithm: query.group_algorithm || 'avg',
          groupBy,
          algorithm: query.algorithm,
          metricUnit: query.metric_unit,
          calculationUnit: query.calculation_unit,
          thresholdUnit: query.threshold_unit,
          role: query.role,
          threshold: query.threshold,
          ...(query.count_predicate ? { countPredicate: query.count_predicate } : {})
        });
      }),
      resultName: condition.result_name || '',
      expression: ''
    };
  }

  if (condition?.type === 'formula') {
    return {
      rows: condition.queries.map((query, index) =>
        createMetricRow(index, {
          ref: query.ref || getMetricRowRef(index),
          metricId: query.metric_id || null,
          ...(storedMetricName(query.metric_name)
            ? { metricName: storedMetricName(query.metric_name) }
            : {}),
          filters: query.filter || [],
          groupAlgorithm: query.group_algorithm || 'avg',
          groupBy: query.group_by?.length ? query.group_by : ['instance_id']
        })
      ),
      resultName: condition.result_name || '',
      expression: condition.expression || DEFAULT_FORMULA_EXPRESSION
    };
  }

  return {
    rows: toMetricRowsFromMetricCondition(
      condition?.type === 'metric' ? condition : undefined,
      options
    ),
    resultName: '',
    expression: DEFAULT_FORMULA_EXPRESSION
  };
};

interface TemplateQuerySource {
  query_condition?: MetricExpressionQueryCondition | Record<string, unknown>;
  metric_name?: string;
  metric_id?: number | null;
  filter?: MetricQueryCondition['filter'];
}

export const resolveTemplateQueryCondition = (
  data: TemplateQuerySource | null | undefined
): MetricExpressionQueryCondition | undefined => {
  if (!data) return undefined;
  const query = data.query_condition;
  if (query && typeof query === 'object' && query.type === 'formula') {
    return query as FormulaQueryCondition;
  }
  if (query && typeof query === 'object' && query.type === 'metric') {
    const metricName = String(
      query.metric_name || data.metric_name || ''
    ).trim();
    return {
      ...(query as MetricQueryCondition),
      ...(metricName ? { metric_name: metricName } : {}),
    };
  }
  if (query && typeof query === 'object' && 'type' in query && query.type) {
    return query as MetricExpressionQueryCondition;
  }
  const metricName = String(data.metric_name || '').trim();
  const metricId = data.metric_id ?? null;
  if (!metricName && metricId == null) {
    return undefined;
  }
  return {
    type: 'metric',
    ...(metricName ? { metric_name: metricName } : {}),
    ...(metricId != null ? { metric_id: metricId } : {}),
    filter: data.filter || [],
  };
};

export const resolveQueryConditionMetricIds = (
  condition: MetricExpressionQueryCondition | undefined,
  metrics: MetricItem[]
): MetricExpressionQueryCondition | undefined => {
  if (!condition || !metrics.length) return condition;
  const resolveId = (metricId?: number | null, metricName?: string) => {
    const catalog = findCatalogMetric(metrics, metricId, metricName);
    if (catalog) return catalog.id;
    if (metricId != null && metricId !== 0) return metricId;
    return metricId;
  };
  if (condition.type === 'formula') {
    return {
      ...condition,
      queries: condition.queries.map((query) => ({
        ...query,
        metric_id: resolveId(query.metric_id, query.metric_name)
      }))
    };
  }
  if (condition.type === 'multi') {
    return {
      ...condition,
      queries: condition.queries.map((query) => {
        if (query.source === 'formula') {
          return {
            ...query,
            operands: (query.operands || []).map((operand) => ({
              ...operand,
              metric_id: resolveId(operand.metric_id, operand.metric_name)
            }))
          };
        }
        return {
          ...query,
          metric_id: resolveId(query.metric_id, query.metric_name)
        };
      })
    };
  }
  if (condition.type === 'metric') {
    return {
      ...condition,
      metric_id: resolveId(condition.metric_id, condition.metric_name)
    };
  }
  return condition;
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

  const anchorRef = normalizedRows[0]?.ref;
  const anchorGroupBy = normalizedRows[0]?.groupBy || [];
  if (anchorRef && !anchorGroupBy.includes('instance_id')) {
    errors.push(`指标 ${anchorRef} 分组维度必须包含 instance_id`);
  }

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

  normalizedRows.forEach((row, index) => {
    if (!expressionRefs.has(row.ref)) {
      errors.push(`指标 ${row.ref} 未在表达式中使用`);
    }
    if (index === 0) {
      return;
    }
    const extra = row.groupBy.filter((item) => !anchorGroupBy.includes(item));
    if (extra.length) {
      errors.push(`指标 ${row.ref} 包含锚点外额外维度：${extra.join(', ')}`);
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
      ...(row.metricName ? { metric_name: row.metricName } : {}),
      filter: row.filters,
      group_algorithm: row.groupAlgorithm,
      group_by: row.groupBy
    }))
  };
};

const MULTI_MIN_CONDITIONS = 2;
const MULTI_MAX_CONDITIONS = 5;
const MULTI_MIRROR_FIELDS = [
  'algorithm',
  'group_algorithm',
  'group_by',
  'metric_unit',
  'calculation_unit',
  'threshold_unit',
  'threshold',
  'compare_mode',
  'compare_value_kind',
  'compare_offset_hours',
  'compare_offset_days',
  'compare_baseline_weeks',
  'count_predicate',
  'forecast_target',
  'forecast_target_unit',
  'forecast_lookback',
  'recovery_threshold'
] as const;

const finiteThresholdValue = (value: number | null | undefined) =>
  typeof value === 'number' && Number.isFinite(value);

const MULTI_LEVEL_ORDER = ['critical', 'error', 'warning'] as const;

const multiLevelName = (level: string): string => {
  if (level === 'critical') return '严重';
  if (level === 'error') return '错误';
  if (level === 'warning') return '警告';
  return level;
};

const isLevelCondition = (row: MetricExpressionRow): boolean =>
  (row.role || 'level') === 'level';

export const multiLevelRows = (rows: MetricExpressionRow[]): string[] => {
  const present = new Set<string>();
  rows.forEach((row) => {
    if (!isLevelCondition(row)) {
      return;
    }
    (row.threshold || []).forEach((item) => {
      if (item.level) {
        present.add(item.level);
      }
    });
  });
  const canonical = new Set<string>(MULTI_LEVEL_ORDER);
  const ordered = MULTI_LEVEL_ORDER.filter((level) => present.has(level));
  const extra = [...present].filter((level) => !canonical.has(level));
  return [...ordered, ...extra];
};

export const setMultiLevelCell = (
  rows: MetricExpressionRow[],
  ref: string,
  level: string,
  patch: { method?: string; value?: number | null }
): MetricExpressionRow[] =>
  rows.map((row) => {
    if (row.ref !== ref || !isLevelCondition(row)) {
      return row;
    }
    const threshold = [...(row.threshold || [])];
    const index = threshold.findIndex((item) => item.level === level);
    if (index < 0) {
      threshold.push({
        level,
        method: patch.method ?? '>',
        value: patch.value ?? null
      });
      return { ...row, threshold };
    }
    const current = threshold[index];
    threshold[index] = {
      ...current,
      ...(patch.method !== undefined ? { method: patch.method } : {}),
      ...(patch.value !== undefined ? { value: patch.value } : {})
    };
    return { ...row, threshold };
  });

export const addMultiLevel = (rows: MetricExpressionRow[]): MetricExpressionRow[] => {
  const present = new Set(multiLevelRows(rows));
  const next = MULTI_LEVEL_ORDER.find((level) => !present.has(level));
  if (!next) {
    return [...rows];
  }
  return rows.map((row) => {
    if (!isLevelCondition(row)) {
      return row;
    }
    const threshold = row.threshold || [];
    if (threshold.some((item) => item.level === next)) {
      return row;
    }
    return {
      ...row,
      threshold: [...threshold, { level: next, method: '>', value: null }]
    };
  });
};

export const removeMultiLevel = (
  rows: MetricExpressionRow[],
  level: string
): MetricExpressionRow[] =>
  rows.map((row) => {
    if (!isLevelCondition(row)) {
      return row;
    }
    const threshold = row.threshold || [];
    if (!threshold.some((item) => item.level === level)) {
      return row;
    }
    return {
      ...row,
      threshold: threshold.filter((item) => item.level !== level)
    };
  });

const validateFormulaConditionRow = (row: MetricExpressionRow): string[] => {
  const errors: string[] = [];
  if (!String(row.resultName || '').trim()) {
    errors.push(`条件 ${row.ref} 必须填写结果名称`);
  }
  const operands = row.operands || [];
  if (operands.length < 2) {
    errors.push(`条件 ${row.ref} 至少需要两个操作数`);
  }
  errors.push(...validateMetricRows(operands));
  if (FORMULA_PER_SERIES_ALGORITHMS.has(row.algorithm || '')) {
    errors.push(`条件 ${row.ref} 不能使用逐序列算法`);
  }
  const expression = String(row.expression || '').trim();
  if (!expression) {
    errors.push(`条件 ${row.ref} 的表达式不能为空`);
    return errors;
  }
  const parsed = parseFormulaExpression(expression);
  errors.push(...parsed.errors.map((message) => `条件 ${row.ref} ${message}`));
  const available = new Set(operands.map((operand) => operand.ref));
  const referenced = new Set(parsed.refs);
  parsed.refs.forEach((ref) => {
    if (!available.has(ref)) {
      errors.push(`条件 ${row.ref} 的表达式引用了不存在的变量：${ref}`);
    }
  });
  if (referenced.size < 2) {
    errors.push(`条件 ${row.ref} 的表达式至少需要引用两个不同变量`);
  }
  operands.forEach((operand) => {
    if (!referenced.has(operand.ref)) {
      errors.push(`条件 ${row.ref} 的指标 ${operand.ref} 未在表达式中使用`);
    }
  });
  const firstGroupBy = operands[0]?.groupBy || [];
  if (operands.length && firstGroupBy.join('\0') !== (row.groupBy || []).join('\0')) {
    errors.push(`条件 ${row.ref} 的 group_by 必须与第一个操作数一致`);
  }
  operands.forEach((operand, index) => {
    if (index === 0) {
      return;
    }
    const extra = (operand.groupBy || []).filter((item) => !firstGroupBy.includes(item));
    if (extra.length) {
      errors.push(`指标 ${operand.ref} 包含锚点外额外维度：${extra.join(', ')}`);
    }
  });
  return errors;
};

const withConditionDimensions = (
  rows: MetricExpressionRow[]
): MetricExpressionRow[] =>
  rows.map((row) => {
    if (row.source !== 'formula') {
      return row;
    }
    const operands = row.operands || [];
    const anchor = operands[0]?.groupBy?.length ? operands[0].groupBy : row.groupBy;
    return {
      ...row,
      groupBy: anchor,
      operands: operands.map((operand, index) =>
        index === 0 ? { ...operand, groupBy: anchor } : operand
      )
    };
  });

export const validateMultiConditionRows = ({
  resultName,
  rows
}: {
  resultName: string;
  rows: MetricExpressionRow[];
}): string[] => {
  const nativeRows = rows.filter((row) => row.source !== 'formula');
  const errors = nativeRows.length ? validateMetricRows(nativeRows) : [];
  rows.filter((row) => row.source === 'formula').forEach((row) => {
    errors.push(...validateFormulaConditionRow(row));
  });
  if (!resultName.trim()) {
    errors.push('多指标条件必须填写结果名称');
  }
  if (rows.length < MULTI_MIN_CONDITIONS || rows.length > MULTI_MAX_CONDITIONS) {
    errors.push('多指标条件需要 2 到 5 条');
  }
  if (!rows.some((row) => (row.role || 'level') === 'level')) {
    errors.push('多指标条件至少需要一个常规条件');
  }
  const anchorGroupBy = new Set(rows[0]?.groupBy || []);
  rows.forEach((row) => {
    const role = row.role || 'level';
    if (!row.algorithm) {
      errors.push(`条件 ${row.ref} 必须选择汇聚方式`);
    }
    if (role === 'gate') {
      const thresholds = row.threshold || [];
      if (thresholds.length !== 1 || thresholds[0]?.level) {
        errors.push(`前置条件 ${row.ref} 只能有一条不带级别的阈值`);
      } else if (!finiteThresholdValue(thresholds[0]?.value) || !thresholds[0]?.method) {
        errors.push(`前置条件 ${row.ref} 的阈值不完整`);
      }
    } else {
      const filled = (row.threshold || []).filter((item) =>
        finiteThresholdValue(item.value)
      );
      const levels = filled.map((item) => item.level).filter(Boolean);
      if (filled.some((item) => !item.level) || levels.length !== filled.length) {
        errors.push(`条件 ${row.ref} 的阈值必须带级别`);
      }
      if (new Set(levels).size !== levels.length) {
        errors.push(`条件 ${row.ref} 的级别不能重复`);
      }
    }
    if (row !== rows[0]) {
      const extra = row.groupBy.filter((item) => !anchorGroupBy.has(item));
      if (extra.length) {
        errors.push(`条件 ${row.ref} 包含锚点外额外维度：${extra.join(', ')}`);
      }
    }
  });
  const levelConditions = rows.filter((row) => isLevelCondition(row));
  const levelsPresent = multiLevelRows(rows);
  if (levelConditions.length && !levelsPresent.length) {
    errors.push('多指标条件至少需要一个级别');
  }
  levelsPresent.forEach((level) => {
    levelConditions.forEach((row) => {
      const complete = (row.threshold || []).some(
        (item) =>
          item.level === level &&
          finiteThresholdValue(item.value) &&
          Boolean(item.method)
      );
      if (!complete) {
        errors.push(`${multiLevelName(level)}级别里条件 ${row.ref} 的阈值不完整`);
      }
    });
  });
  return errors;
};

export const buildMultiQueryCondition = ({
  resultName,
  rows
}: {
  resultName: string;
  rows: MetricExpressionRow[];
}): MultiQueryCondition => {
  const normalizedRows = withConditionDimensions(assignMetricRowRefs(rows));
  const errors = validateMultiConditionRows({ resultName, rows: normalizedRows });
  if (errors.length) {
    throw new Error(errors.join('；'));
  }
  return {
    type: 'multi',
    result_name: resultName.trim(),
    combinator: 'all',
    queries: normalizedRows.map((row) => {
      const threshold = (row.threshold || [])
        .filter((item) => finiteThresholdValue(item.value))
        .map((item) => ({
          ...(item.level ? { level: item.level } : {}),
          method: item.method,
          value: item.value
        }));
      const countPredicate =
        row.algorithm === 'count_if_over_time' && row.countPredicate?.method
          ? { count_predicate: row.countPredicate }
          : {};
      if (row.source === 'formula') {
        return {
          ref: row.ref,
          source: 'formula' as const,
          metric_name: String(row.resultName || '').trim(),
          expression: String(row.expression || '').trim(),
          operands: (row.operands || []).map((operand) => ({
            ref: operand.ref,
            metric_id: operand.metricId,
            ...(operand.metricName ? { metric_name: operand.metricName } : {}),
            filter: operand.filters,
            group_algorithm: operand.groupAlgorithm,
            group_by: operand.groupBy
          })),
          group_by: row.groupBy,
          algorithm: row.algorithm || '',
          metric_unit: '',
          calculation_unit: row.calculationUnit || '',
          threshold_unit: row.thresholdUnit || '',
          role: row.role || 'level',
          threshold,
          ...countPredicate
        };
      }
      return {
        ref: row.ref,
        metric_id: row.metricId,
        ...(row.metricName ? { metric_name: row.metricName } : {}),
        filter: row.filters,
        group_algorithm: row.groupAlgorithm,
        group_by: row.groupBy,
        algorithm: row.algorithm || '',
        metric_unit: row.metricUnit || '',
        calculation_unit: row.calculationUnit || '',
        threshold_unit: row.thresholdUnit || '',
        role: row.role || 'level',
        threshold,
        ...countPredicate
      };
    })
  };
};

export const omitMultiMirrorFields = <T extends Record<string, unknown>>(params: T): T => {
  const next = { ...params };
  MULTI_MIRROR_FIELDS.forEach((field) => {
    delete next[field];
  });
  return next;
};

const conditionDisplayName = (
  row: MetricExpressionRow,
  unnamedResult: string
): string => {
  const operandName =
    row.operands?.find((operand) => operand.metricLabel || operand.metricName)
      ?.metricLabel ||
    row.operands?.find((operand) => operand.metricName)?.metricName;
  if (row.source === 'formula') {
    return row.resultName || operandName || unnamedResult;
  }
  return row.metricLabel || row.metricName || row.ref;
};

const thresholdClause = (
  row: MetricExpressionRow,
  threshold: { method?: string; value?: number | null } | undefined,
  unsetThreshold: string
): string => {
  const name = conditionDisplayName(row, '');
  const unit = row.thresholdUnit || '';
  if (!threshold || !finiteThresholdValue(threshold.value) || !threshold.method) {
    return `${name} ${unsetThreshold}`.trim();
  }
  return `${name} ${threshold.method} ${threshold.value ?? ''}${unit}`.trim();
};

export const buildMultiConditionSentence = (
  rows: MetricExpressionRow[],
  labels?: {
    and?: string;
    levelNames?: Record<string, string>;
    gate?: string;
    unsetThreshold?: string;
    unnamedResult?: string;
  }
): string => {
  const joiner = labels?.and || '且';
  const levelNames = labels?.levelNames || {
    info: '信息',
    warning: '警告',
    error: '错误',
    critical: '严重'
  };
  const gateLabel = labels?.gate || '前置条件';
  const unsetThreshold = labels?.unsetThreshold || '未设阈值';
  const unnamedResult = labels?.unnamedResult || '未命名结果';
  const namedRows = rows.map((row) => (
    row.source === 'formula' && !row.resultName
      ? { ...row, resultName: conditionDisplayName(row, unnamedResult) }
      : row
  ));
  const levelConditions = namedRows.filter(isLevelCondition);
  const gateConditions = namedRows.filter((row) => row.role === 'gate');
  const levels = multiLevelRows(namedRows);
  const levelParts = levels.length
    ? levels.map((level) => {
      const cells = levelConditions.map((row) =>
        thresholdClause(
          row,
          (row.threshold || []).find((item) => item.level === level),
          unsetThreshold
        )
      );
      return `${levelNames[level] || level}：${cells.join(` ${joiner} `)}`;
    })
    : levelConditions.map((row) => thresholdClause(row, undefined, unsetThreshold));
  const gateParts = gateConditions.map((row) =>
    `${gateLabel}：${thresholdClause(row, row.threshold?.[0], unsetThreshold)}`
  );
  return [...levelParts, ...gateParts].join('；');
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
  if (mode === 'multi') {
    return buildMultiQueryCondition({ resultName, rows });
  }
  const shouldBuildFormula = mode === 'formula';

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
    ...(row.metricName ? { metric_name: row.metricName } : {}),
    filter: row.filters
  };
};

const findMetricForRow = (
  row: MetricExpressionRow,
  metrics: MetricItem[]
): MetricItem | undefined =>
  metrics.find(
    (item) =>
      (row.metricId != null && String(item.id) === String(row.metricId)) ||
      (!!row.metricName && item.name === row.metricName)
  );

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
  threshold = [],
  calculationUnit,
  thresholdUnit,
  compareMode,
  compareValueKind,
  countPredicate,
  forecastTarget,
  forecastTargetUnit,
  forecastLookback,
  compareOffsetHours
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
  threshold?: ThresholdField[];
  calculationUnit?: string | null;
  thresholdUnit?: string | null;
  compareMode?: string | null;
  compareValueKind?: string | null;
  countPredicate?: { method?: string; value?: number | null } | null;
  forecastTarget?: number | null;
  forecastTargetUnit?: string | null;
  forecastLookback?: { type: string; value: number } | null;
  compareOffsetHours?: number | null;
}) => {
  if (mode === 'multi') {
    if (!monitorObjId || !selectedInstance) {
      return null;
    }
    const queryCondition = buildMultiQueryCondition({ resultName, rows });
    rows.forEach((row) => {
      const carriers = row.source === 'formula' ? row.operands || [] : [row];
      if (carriers.some((item) => !findMetricForRow(item, metrics))) {
        throw new Error(METRIC_NOT_READY_MESSAGE);
      }
    });
    return {
      monitor_object: monitorObjId,
      query_condition: queryCondition,
      source,
      period: {
        type: periodUnit,
        value: period || 5
      },
      preview: {
        instance_id: selectedInstance.instance_id,
        instance_id_values: selectedInstance.instance_id_values,
        duration_points: 30
      }
    };
  }

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
  if (isFormula) {
    queryCondition.queries.forEach((query, index) => {
      const row = rows.find((item) => item.ref === query.ref) || rows[index];
      const metric = row ? findMetricForRow(row, metrics) : undefined;
      if (!metric) {
        throw new Error(METRIC_NOT_READY_MESSAGE);
      }
    });
  }

  const previewQueryCondition = queryCondition;
  const payloadGroupBy = isFormula
    ? sanitizeGroupBy(anchorRow.groupBy || [])
    : sanitizeGroupBy(groupBy);
  const payloadGroupAlgorithm = isFormula
    ? anchorRow.groupAlgorithm || 'avg'
    : groupAlgorithm || 'avg';
  const units = resolveMetricExpressionUnits({
    queryType: isFormula ? 'formula' : 'metric',
    metricUnit: anchorMetric.unit,
    calculationUnit,
    thresholdUnit
  });
  const resolvedCompareMode = compareMode || 'absolute';
  const resolvedCompareKind =
    resolvedCompareMode === 'absolute' ? '' : compareValueKind || '';
  const previewThresholdUnit =
    resolvedCompareKind === 'percent'
      ? 'percent'
      : resolvedCompareKind === 'ratio'
        ? ''
        : units.thresholdUnit;

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
    threshold: threshold.filter(
      (item) => item.value !== null && item.value !== undefined
    ),
    metric_unit: units.metricUnit,
    calculation_unit: units.calculationUnit,
    threshold_unit: previewThresholdUnit,
    compare_mode: resolvedCompareMode,
    compare_value_kind: resolvedCompareKind,
    compare_offset_hours:
      resolvedCompareMode === 'offset_hours' &&
      compareOffsetHours != null &&
      Number.isFinite(compareOffsetHours) &&
      compareOffsetHours >= 1
        ? Math.floor(compareOffsetHours)
        : null,
    compare_offset_days:
      (resolvedCompareMode === 'offset_days' ||
        resolvedCompareMode === 'baseline_days') &&
      compareOffsetHours != null &&
      Number.isFinite(compareOffsetHours) &&
      compareOffsetHours >= 1
        ? Math.floor(compareOffsetHours)
        : null,
    compare_baseline_weeks:
      resolvedCompareMode === 'baseline_weeks' &&
      compareOffsetHours != null &&
      Number.isFinite(compareOffsetHours) &&
      compareOffsetHours >= 1
        ? Math.floor(compareOffsetHours)
        : null,
    count_predicate:
      algorithm === 'count_if_over_time' && countPredicate?.method
        ? {
          method: countPredicate.method,
          value: countPredicate.value
        }
        : {},
    forecast_target:
      resolvedCompareMode === 'timeleft' ? forecastTarget ?? null : null,
    forecast_target_unit:
      resolvedCompareMode === 'timeleft' ? forecastTargetUnit || '' : '',
    forecast_lookback:
      resolvedCompareMode === 'timeleft'
        ? forecastLookback || { type: 'hour', value: 1 }
        : {},
    preview: {
      instance_id: selectedInstance.instance_id,
      instance_id_values: selectedInstance.instance_id_values,
      duration_points: 30
    }
  };
};
