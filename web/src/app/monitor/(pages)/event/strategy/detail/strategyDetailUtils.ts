import {
  CascaderItem,
  GroupedUnitList,
  MetricItem,
  SegmentedItem,
  UnitListItem
} from '@/app/monitor/types';
import { isStringArray } from '@/app/monitor/utils/common';
import { getMonitorUnitSelectLabel } from '@/app/monitor/components/monitor-shared/unit-label';
import { MetricExpressionMode } from './formulaExpressionUtils';

export const FORMULA_DEFAULT_RESULT_UNIT = 'percent';

/** 兼容策略阈值下拉与本地验证脚本。 */
export const getThresholdUnitSelectLabel = getMonitorUnitSelectLabel;

/** 组织变更后，剔除不再属于候选用户列表的已选通知人 */
export const pruneNoticeUsers = <T extends string | number>(
  noticeUsers: T[] | undefined,
  userList: Array<{ id: string | number; username?: string }>
): T[] => {
  if (!Array.isArray(noticeUsers) || !noticeUsers.length) {
    return [];
  }
  if (!Array.isArray(userList) || !userList.length) {
    return [];
  }

  const allowed = new Set<string>();
  userList.forEach((user) => {
    allowed.add(String(user.id));
    if (user.username) {
      allowed.add(user.username);
    }
  });

  return noticeUsers.filter((item) => allowed.has(String(item)));
};

/** 开启通知且所选渠道中存在需要通知人的渠道时，通知人必填 */
export const shouldRequireNoticeUsers = ({
  notice,
  noticeTypeIds,
  channelList
}: {
  notice?: boolean;
  noticeTypeIds?: Array<string | number>;
  channelList: Array<{ id: string | number; channel_type: string }>;
}): boolean => {
  if (!notice) return false;
  const selectedIds = noticeTypeIds || [];
  if (!selectedIds.length) return false;
  const selectedChannels = channelList.filter((channel) =>
    selectedIds.some((id) => String(id) === String(channel.id))
  );
  if (!selectedChannels.length) return false;
  return selectedChannels.some((channel) => channel.channel_type !== 'nats');
};

/** 通知人表单项刚出现且仍为空时，把已选处理人带入；调用方负责只做一次。 */
export const seedNoticeUsersFromHandlers = <T>(
  noticeUsers: T[] | undefined,
  handlers: T[] | undefined
): T[] | null => {
  if (Array.isArray(noticeUsers) && noticeUsers.length) {
    return null;
  }
  if (!Array.isArray(handlers) || !handlers.length) {
    return null;
  }
  return [...handlers];
};

const INVALID_THRESHOLD_UNIT_IDS = new Set(['none', 'short']);

/** 无量纲 / 不参与阈值单位选配的单位（none、short、空） */
export const isVacantThresholdUnit = (
  unit: string | null | undefined
): boolean => !unit || INVALID_THRESHOLD_UNIT_IDS.has(unit);

/** 从策略 query_condition 抽出 metric_id（metric / formula）。 */
export const extractMetricIdsFromQueryCondition = (
  queryCondition:
    | {
        type?: string;
        metric_id?: number | null;
        queries?: Array<{ metric_id?: number | null }>;
      }
    | null
    | undefined
): number[] => {
  if (!queryCondition || typeof queryCondition !== 'object') return [];
  if (queryCondition.type === 'formula' && Array.isArray(queryCondition.queries)) {
    const ids = queryCondition.queries
      .map((q) => q?.metric_id)
      .filter((id): id is number => id != null && Number.isFinite(Number(id)) && Number(id) !== 0)
      .map((id) => Number(id));
    return [...new Set(ids)];
  }
  if (queryCondition.type === 'metric' || queryCondition.metric_id != null) {
    const id = queryCondition.metric_id;
    if (id != null && Number.isFinite(Number(id)) && Number(id) !== 0) {
      return [Number(id)];
    }
  }
  return [];
};

/** 指标上的 monitor_plugin 反查插件：仅当唯一且落在 pluginList 内才返回。 */
export const resolvePluginIdFromMetricPlugins = (
  pluginList: SegmentedItem[],
  metrics: Array<{ monitor_plugin?: string | number | null }>
): string | number | undefined => {
  if (!pluginList.length || !metrics.length) return undefined;
  const pluginIds = [
    ...new Set(
      metrics
        .map((m) => m?.monitor_plugin)
        .filter((id) => id != null && id !== '')
        .map((id) => String(id))
    ),
  ];
  if (pluginIds.length !== 1) return undefined;
  const matched = pluginList.find((item) => String(item.value) === pluginIds[0]);
  return matched?.value;
};

export const resolveInitialMetricPluginId = ({
  type,
  pluginList,
  policyCollectType,
  policyDetailReady = false,
  metricResolvedPluginId,
}: {
  type: string;
  pluginList: SegmentedItem[];
  policyCollectType?: string | number | null;
  policyDetailReady?: boolean;
  /** 由 metric→plugin 反查得到的唯一插件，可覆盖空/无效 collect_type */
  metricResolvedPluginId?: string | number | null;
}): string | number | undefined => {
  if (!pluginList.length) return undefined;
  const pickMetricFallback = () => {
    if (metricResolvedPluginId == null || metricResolvedPluginId === '') {
      return undefined;
    }
    return pluginList.find(
      (item) => String(item.value) === String(metricResolvedPluginId)
    )?.value;
  };
  if (!['add', 'builtIn'].includes(type)) {
    if (policyCollectType == null || policyCollectType === '') {
      // 详情未到时 collect_type 一定为空，不能猜第一个插件；多插件对象也不猜。
      if (policyDetailReady && pluginList.length === 1) {
        return pluginList[0]?.value;
      }
      if (policyDetailReady) {
        return pickMetricFallback();
      }
      return undefined;
    }
    const matched = pluginList.find(
      (item) => String(item.value) === String(policyCollectType)
    );
    if (matched) return matched.value;
    // 无效/过期 collect_type：禁止落到列表第一个，优先用 metric 反查。
    return pickMetricFallback();
  }
  return pluginList[0]?.value;
};

/** 编辑回填表单里的采集插件：空值且对象只有一个插件时补上，避免再存成空串。 */
export const resolveEditFormCollectType = (
  policyCollectType: string | number | null | undefined,
  pluginList: SegmentedItem[],
  metricResolvedPluginId?: string | number | null
): string | number => {
  const pickMetricFallback = () => {
    if (metricResolvedPluginId == null || metricResolvedPluginId === '') {
      return '';
    }
    const matched = pluginList.find(
      (item) => String(item.value) === String(metricResolvedPluginId)
    );
    return matched ? matched.value : '';
  };
  if (policyCollectType != null && policyCollectType !== '') {
    const matched = pluginList.find(
      (item) => String(item.value) === String(policyCollectType)
    );
    if (matched) return +matched.value;
    const fromMetric = pickMetricFallback();
    return fromMetric === '' ? '' : fromMetric;
  }
  if (pluginList.length === 1) {
    return pluginList[0].value;
  }
  return pickMetricFallback();
};

/** 编辑态何时跑指标回填：目录已到，或策略详情已到（可按 id 补名称）。 */
export const shouldHydrateMetricOnEdit = ({
  type,
  initMetricCount,
  policyId,
}: {
  type: string;
  initMetricCount: number;
  policyId?: number | string | null;
}): boolean => {
  if (['builtIn', 'add'].includes(type)) return false;
  return initMetricCount > 0 || policyId != null;
};

export const getValidThresholdUnitOptions = (
  unitList: UnitListItem[]
): UnitListItem[] =>
  unitList.filter((item) => !INVALID_THRESHOLD_UNIT_IDS.has(item.unit_id));

export const resolveFormulaResultUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string | null => {
  const validUnits = getValidThresholdUnitOptions(unitList);
  if (!validUnits.length) {
    // 契约:单位表未就绪时,绝不硬塞默认单位
    return null;
  }
  const unitIds = new Set(validUnits.map((item) => item.unit_id));

  if (unit && unitIds.has(unit)) {
    return unit;
  }

  return FORMULA_DEFAULT_RESULT_UNIT;
};

export const getCalculationUnitOnMetricRowsChange = ({
  previousMode,
  nextMode,
  currentCalculationUnit,
  unitList,
}: {
  previousMode: MetricExpressionMode;
  nextMode: MetricExpressionMode;
  currentCalculationUnit: string | null;
  unitList: UnitListItem[];
}): string | null => {
  if (nextMode !== 'formula') {
    return currentCalculationUnit;
  }

  // 单位表未就绪:
  //  - 首次进入 formula 时返回 null,让 UI 提示用户重选
  //  - 已在 formula 模式时保留用户已选值,避免在 unitList 抖动时被覆盖
  if (!getValidThresholdUnitOptions(unitList).length) {
    return previousMode === 'formula' ? currentCalculationUnit : null;
  }

  if (previousMode !== 'formula') {
    return FORMULA_DEFAULT_RESULT_UNIT;
  }

  return resolveFormulaResultUnit(currentCalculationUnit, unitList);
};

interface EnumOption {
  id: number;
  name: string;
  color?: string;
}

// 内部 JSON 解析:对脏数据(非 JSON / 非数组 / 缺 id/name / id 非法)统一兜底成空数组,
// 避免渲染层因为 key=NaN 或 name=[object Object] 抛错。
const parseEnumOptions = (input: string): EnumOption[] => {
  try {
    const parsed: unknown = JSON.parse(input);
    if (!Array.isArray(parsed)) return [];
    const out: EnumOption[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue;
      const idNum = Number((item as { id: unknown }).id);
      const name = (item as { name: unknown }).name;
      if (!Number.isFinite(idNum)) continue;
      if (typeof name !== 'string' || !name) continue;
      const color = (item as { color?: unknown }).color;
      out.push({
        id: idNum,
        name,
        ...(typeof color === 'string' ? { color } : {})
      });
    }
    return out;
  } catch {
    return [];
  }
};

export const getMetricThresholdEnumState = ({
  isFormulaMode,
  metricUnit,
}: {
  isFormulaMode: boolean;
  metricUnit: string | null;
}): {
  isEnumMetric: boolean;
  enumOptions: EnumOption[];
} => {
  // 公式模式:阈值永远用数字,即使 metricUnit 形态上是枚举也忽略
  if (isFormulaMode || !metricUnit || !isStringArray(metricUnit)) {
    return {
      isEnumMetric: false,
      enumOptions: []
    };
  }

  const options = parseEnumOptions(metricUnit);
  return {
    isEnumMetric: options.length > 0,
    enumOptions: options
  };
};

export const shouldShowThresholdUnitSelector = ({
  isEnumMetric,
  calculationUnit,
  unitList = [],
}: {
  isFormulaMode: boolean;
  isEnumMetric: boolean;
  calculationUnit?: string | null;
  unitList?: UnitListItem[];
}): boolean => {
  if (isEnumMetric) return false;
  if (isVacantThresholdUnit(calculationUnit)) return false;
  // 单位表就绪但无可选阈值单位时也不展示（避免空下拉 + 必填）
  if (
    unitList.length > 0 &&
    !getThresholdUnitOptions({
      unitList,
      metricUnit: calculationUnit ?? null,
      isEnumMetric: false,
    }).length
  ) {
    return false;
  }
  return true;
};

export const getThresholdUnitOptions = ({
  unitList,
  metricUnit,
  isEnumMetric,
  lockToExactUnit = false,
}: {
  unitList: UnitListItem[];
  metricUnit: string | null;
  isEnumMetric: boolean;
  lockToExactUnit?: boolean;
}): UnitListItem[] => {
  if (isEnumMetric || !metricUnit || isVacantThresholdUnit(metricUnit)) {
    return [];
  }

  const validUnits = getValidThresholdUnitOptions(unitList);
  const baseUnit = validUnits.find((item) => item.unit_id === metricUnit);
  if (!baseUnit) return [];

  if (lockToExactUnit || baseUnit.system === null) {
    return validUnits.filter((item) => item.unit_id === baseUnit.unit_id);
  }

  return validUnits.filter((item) => item.system === baseUnit.system);
};

/** 容量线单位：沿用已选的同量纲单位，否则回到指标原始单位。公式结果没有单一原始单位，不开放选择。 */
export const resolveForecastTargetUnit = ({
  isFormulaMode,
  metricUnit,
  forecastTargetUnit,
  unitOptions,
}: {
  isFormulaMode: boolean;
  metricUnit?: string | null;
  forecastTargetUnit?: string | null;
  unitOptions: UnitListItem[];
}): string => {
  if (isFormulaMode || !unitOptions.length) return '';
  if (
    forecastTargetUnit &&
    unitOptions.some((item) => item.unit_id === forecastTargetUnit)
  ) {
    return forecastTargetUnit;
  }
  if (metricUnit && unitOptions.some((item) => item.unit_id === metricUnit)) {
    return metricUnit;
  }
  return unitOptions[0]?.unit_id || '';
};

export const resolveThresholdUnit = ({
  thresholdUnit,
  calculationUnit,
  unitList,
}: {
  thresholdUnit: string | null | undefined;
  calculationUnit: string | null | undefined;
  unitList: UnitListItem[];
}): string | null => {
  // 单位表尚未加载时保留接口中的历史值，避免初始化过程误覆盖。
  if (!unitList.length) return thresholdUnit || calculationUnit || null;
  if (!calculationUnit) return thresholdUnit || null;

  const options = getThresholdUnitOptions({
    unitList,
    metricUnit: calculationUnit,
    isEnumMetric: false,
  });
  if (thresholdUnit && options.some((item) => item.unit_id === thresholdUnit)) {
    return thresholdUnit;
  }
  return options.some((item) => item.unit_id === calculationUnit)
    ? calculationUnit
    : null;
};

export const getThresholdUnitOnCalculationUnitChange = resolveThresholdUnit;

/** percentunit(0–1) ↔ percent(0–100) 切换时的数值缩放因子；其他单位对返回 null。 */
export const getPercentUnitScaleFactor = (
  fromUnit: string | null | undefined,
  toUnit: string | null | undefined
): number | null => {
  if (!fromUnit || !toUnit || fromUnit === toUnit) return null;
  if (fromUnit === 'percentunit' && toUnit === 'percent') return 100;
  if (fromUnit === 'percent' && toUnit === 'percentunit') return 0.01;
  return null;
};

/** 百分比阈值输入占位，明示量纲；其他单位不提示。 */
export const getThresholdValuePlaceholder = (
  thresholdUnit: string | null | undefined
): string => {
  if (thresholdUnit === 'percent') return '0-100';
  if (thresholdUnit === 'percentunit') return '0.0-1.0';
  return '';
};

/** 阈值单位在 percentunit↔percent 间切换时同步缩放数值，避免误报/漏报。 */
export const scaleThresholdValuesForUnitChange = <T extends { value: number | null }>(
  thresholds: T[],
  fromUnit: string | null | undefined,
  toUnit: string | null | undefined
): T[] => {
  const factor = getPercentUnitScaleFactor(fromUnit, toUnit);
  if (factor == null) return thresholds;
  return thresholds.map((item) => ({
    ...item,
    value: item.value == null ? null : item.value * factor
  }));
};

// 把 groupedUnitList (按 category 分组) 转为 Cascader 选项;
// 一级 value = category 名,二级 value = unit_id,二级为叶子节点需 children=[] 以满足 CascaderItem 递归类型。
// 单位表规模小 (<100),即便 O(N×M) 也可接受。
export const buildMetricUnitCascaderOptions = (
  groupedUnitList: GroupedUnitList[]
): CascaderItem[] =>
  groupedUnitList
    .map((group) => ({
      label: group.label,
      value: group.label,
      children: (group.children || [])
        .filter((item) => !INVALID_THRESHOLD_UNIT_IDS.has(item.value))
        .map((item) => ({
          label: getMonitorUnitSelectLabel({
            unit_id: String(item.value),
            unit_name: item.label,
            display_unit: item.unit
          }),
          value: item.value,
          children: []
        }))
    }))
    .filter((group) => group.children.length > 0);

export const resolveMetricDisplayUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string => {
  if (isVacantThresholdUnit(unit) || isStringArray(unit || '')) {
    return '';
  }

  return unitList.find((item) => item.unit_id === unit)?.display_unit || '';
};

export const resolvePreviewChartUnit = (
  responseUnit: string | null | undefined,
  thresholdUnit: string | null | undefined,
  calculationUnit: string | null | undefined
): string | null => responseUnit || thresholdUnit || calculationUnit || null;

export const COMPARE_MODE_ABSOLUTE = 'absolute';
export const COMPARE_MODE_PREVIOUS_WINDOW = 'previous_window';
export const COMPARE_MODE_OFFSET_1H = 'offset_1h';
export const COMPARE_MODE_OFFSET_24H = 'offset_24h';
export const COMPARE_MODE_OFFSET_HOURS = 'offset_hours';
export const COMPARE_MODE_OFFSET_DAYS = 'offset_days';
export const COMPARE_MODE_BASELINE_DAYS = 'baseline_days';
export const MAX_COMPARE_OFFSET_HOURS = 8760;
export const MAX_COMPARE_OFFSET_DAYS = 365;
export const MAX_COMPARE_BASELINE_WEEKS = 52;
export const COMPARE_MODE_OFFSET_7D = 'offset_7d';
export const COMPARE_MODE_OFFSET_30D = 'offset_30d';
export const COMPARE_MODE_BASELINE_WEEKS = 'baseline_weeks';
export const COMPARE_MODE_BASELINE_4W = 'baseline_4w';
export const COMPARE_MODE_TIMELEFT = 'timeleft';
export const LOW_SIDE_THRESHOLD_METHODS = new Set(['<', '<=']);

export const isFilledThresholdValue = (value: unknown): boolean => {
  if (typeof value === 'boolean' || value == null || value === '') {
    return false;
  }
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number);
};

export const completedThresholds = <
  T extends { method?: string | null; value?: unknown }
>(
    thresholds: T[] | null | undefined
  ): T[] => (thresholds || []).filter((item) => isFilledThresholdValue(item.value));

export const timeleftRequiresLowSideThresholds = (
  compareMode: string | null | undefined,
  thresholds: Array<{ method?: string | null }> | null | undefined
): boolean => {
  if (compareMode !== COMPARE_MODE_TIMELEFT) {
    return true;
  }
  return (thresholds || []).every(
    (item) => !item.method || LOW_SIDE_THRESHOLD_METHODS.has(item.method)
  );
};

export const ENABLED_COMPARE_MODES = [
  COMPARE_MODE_ABSOLUTE,
  COMPARE_MODE_PREVIOUS_WINDOW,
  COMPARE_MODE_OFFSET_HOURS,
  COMPARE_MODE_OFFSET_DAYS,
  COMPARE_MODE_BASELINE_DAYS,
  COMPARE_MODE_BASELINE_WEEKS,
  COMPARE_MODE_TIMELEFT
] as const;

export const COMPARE_VALUE_KIND_DELTA = 'delta';
export const COMPARE_VALUE_KIND_PERCENT = 'percent';
export const COMPARE_VALUE_KIND_RATIO = 'ratio';

const COMPARE_RESTATEMENT_BASELINE_KEYS: Record<
  string,
  { key: string; fallback: string }
> = {
  [COMPARE_MODE_PREVIOUS_WINDOW]: {
    key: 'monitor.events.compareModePreviousWindowRestate',
    fallback: '上一等长窗'
  },
  [COMPARE_MODE_OFFSET_1H]: {
    key: 'monitor.events.compareModeOffset1hRestate',
    fallback: '1 小时前'
  },
  [COMPARE_MODE_OFFSET_24H]: {
    key: 'monitor.events.compareModeOffset24hRestate',
    fallback: '24 小时前'
  },
  [COMPARE_MODE_OFFSET_7D]: {
    key: 'monitor.events.compareModeOffset7dRestate',
    fallback: '上周同期'
  },
  [COMPARE_MODE_OFFSET_30D]: {
    key: 'monitor.events.compareModeOffset30dRestate',
    fallback: '30 天前'
  },
  [COMPARE_MODE_BASELINE_4W]: {
    key: 'monitor.events.compareModeBaseline4wRestate',
    fallback: '近 4 周同窗均值'
  }
};
export const COMPARE_VALUE_KIND_HOURS = 'hours';
export const COUNT_IF_ALGORITHM = 'count_if_over_time';
export const PER_SERIES_ALGORITHMS = ['rate', 'changes', 'deriv'];
export const RATE_FUNCTION_RE = /\b(?:rate|irate|increase)\s*\(/i;
const DATA_BYTE_UNITS = [
  'bytes',
  'kibibytes',
  'mebibytes',
  'gibibytes',
  'tebibytes',
  'pebibytes'
] as const;
const DATA_BYTE_RATE_UNITS = [
  'byteps',
  'kibyteps',
  'mibyteps',
  'gibyteps',
  'tibyteps',
  'pibyteps'
] as const;
const DATA_BIT_UNITS = [
  'bits',
  'kilobits',
  'megabits',
  'gigabits',
  'terabits',
  'petabits'
] as const;
const DATA_BIT_RATE_UNITS = [
  'bitps',
  'kbitps',
  'mbitps',
  'gbitps',
  'tbitps',
  'pbitps'
] as const;
const QUANTITY_TO_RATE_UNIT: Record<string, string> = {
  ...Object.fromEntries(
    DATA_BYTE_UNITS.map((unit, index) => [unit, DATA_BYTE_RATE_UNITS[index]])
  ),
  ...Object.fromEntries(
    DATA_BIT_UNITS.map((unit, index) => [unit, DATA_BIT_RATE_UNITS[index]])
  ),
  counts: 'cps',
  count: 'cps'
};
const ALREADY_PER_SECOND_UNITS = new Set<string>([
  ...DATA_BYTE_RATE_UNITS,
  ...DATA_BIT_RATE_UNITS,
  'cps',
  'msps',
  'hertz',
  'kilohertz',
  'megahertz'
]);
export const NEW_ALGORITHMS = [
  'p90_over_time',
  'p95_over_time',
  'p99_over_time',
  'stddev_over_time',
  'count_if_over_time',
  'rate',
  'changes',
  'deriv'
];

/** 括号里用第一版下拉的方法全称（大写），方便对上旧策略。 */
export const getAlgorithmShortName = (
  algorithm: string | null | undefined
): string => {
  if (!algorithm) return '';
  return String(algorithm).toUpperCase();
};

export const formatAlgorithmDisplayLabel = (
  localeLabel: string,
  algorithm: string | null | undefined
): string => {
  const shortName = getAlgorithmShortName(algorithm);
  const normalizedLabel = localeLabel.trim().toUpperCase();
  if (!shortName || normalizedLabel === shortName) {
    return localeLabel;
  }
  return `${localeLabel}（${shortName}）`;
};
export const LEVEL_ALGORITHMS = [
  'avg',
  'max',
  'min',
  'last',
  'avg_over_time',
  'max_over_time',
  'min_over_time',
  'last_over_time'
];
export const FORECAST_LOOKBACK_OPTIONS = [
  { type: 'hour', value: 1 },
  { type: 'hour', value: 4 },
  { type: 'hour', value: 24 }
] as const;
export const DEFAULT_FORECAST_LOOKBACK = { type: 'hour', value: 1 };
const COMPARE_OFFSET_SECONDS: Record<string, number> = {
  [COMPARE_MODE_OFFSET_1H]: 3600,
  [COMPARE_MODE_OFFSET_24H]: 86400,
  [COMPARE_MODE_OFFSET_7D]: 7 * 86400,
  [COMPARE_MODE_OFFSET_30D]: 30 * 86400
};

export const COMPARE_VALUE_KINDS_BY_MODE: Record<string, string[]> = {
  [COMPARE_MODE_ABSOLUTE]: [''],
  [COMPARE_MODE_PREVIOUS_WINDOW]: [
    COMPARE_VALUE_KIND_DELTA,
    COMPARE_VALUE_KIND_PERCENT
  ],
  [COMPARE_MODE_OFFSET_1H]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_OFFSET_24H]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_OFFSET_HOURS]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_OFFSET_DAYS]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_BASELINE_DAYS]: [
    COMPARE_VALUE_KIND_DELTA,
    COMPARE_VALUE_KIND_PERCENT
  ],
  [COMPARE_MODE_OFFSET_7D]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_OFFSET_30D]: [
    COMPARE_VALUE_KIND_PERCENT,
    COMPARE_VALUE_KIND_RATIO
  ],
  [COMPARE_MODE_BASELINE_WEEKS]: [
    COMPARE_VALUE_KIND_DELTA,
    COMPARE_VALUE_KIND_PERCENT
  ],
  [COMPARE_MODE_BASELINE_4W]: [
    COMPARE_VALUE_KIND_DELTA,
    COMPARE_VALUE_KIND_PERCENT
  ],
  [COMPARE_MODE_TIMELEFT]: [COMPARE_VALUE_KIND_HOURS]
};

export const policyPeriodToSeconds = (
  type?: string | null,
  value?: number | null
): number | null => {
  if (value == null || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  if (type === 'min') return value * 60;
  if (type === 'hour') return value * 3600;
  if (type === 'day') return value * 86400;
  return null;
};

export const compareSpanSpec = (
  mode?: string | null
): { min: number; max: number; fallback: number } | null => {
  if (mode === COMPARE_MODE_OFFSET_HOURS) {
    return { min: 1, max: MAX_COMPARE_OFFSET_HOURS, fallback: 1 };
  }
  if (mode === COMPARE_MODE_OFFSET_DAYS) {
    return { min: 1, max: MAX_COMPARE_OFFSET_DAYS, fallback: 7 };
  }
  if (mode === COMPARE_MODE_BASELINE_DAYS) {
    return { min: 2, max: MAX_COMPARE_OFFSET_DAYS, fallback: 7 };
  }
  if (mode === COMPARE_MODE_BASELINE_WEEKS) {
    return { min: 2, max: MAX_COMPARE_BASELINE_WEEKS, fallback: 4 };
  }
  return null;
};

export const COMPARE_BASELINE_YOY = 'yoy';

export const compareBaselineFamily = (mode?: string | null): string => {
  if (
    mode === COMPARE_MODE_OFFSET_HOURS ||
    mode === COMPARE_MODE_OFFSET_DAYS ||
    mode === COMPARE_MODE_BASELINE_DAYS ||
    mode === COMPARE_MODE_BASELINE_WEEKS ||
    mode === COMPARE_MODE_OFFSET_1H ||
    mode === COMPARE_MODE_OFFSET_24H ||
    mode === COMPARE_MODE_OFFSET_7D ||
    mode === COMPARE_MODE_OFFSET_30D ||
    mode === COMPARE_MODE_BASELINE_4W
  ) {
    return COMPARE_BASELINE_YOY;
  }
  if (mode === COMPARE_MODE_PREVIOUS_WINDOW) {
    return COMPARE_MODE_PREVIOUS_WINDOW;
  }
  if (mode === COMPARE_MODE_TIMELEFT) {
    return COMPARE_MODE_TIMELEFT;
  }
  return COMPARE_MODE_ABSOLUTE;
};

const normalizeCompareSpan = (
  value: number | null | undefined,
  fallback: number
): number =>
  value != null && Number.isFinite(value) && value >= 1
    ? Math.floor(value)
    : fallback;

export const compareOffsetHoursConflict = (
  hours: number | null | undefined,
  periodType?: string | null,
  periodValue?: number | null
): boolean =>
  compareSpanConflict(COMPARE_MODE_OFFSET_HOURS, hours, periodType, periodValue);

export const compareSpanConflict = (
  mode: string | null | undefined,
  amount: number | null | undefined,
  periodType?: string | null,
  periodValue?: number | null
): boolean => {
  if (amount == null || !Number.isFinite(amount) || amount < 1) {
    return false;
  }
  const periodSeconds = policyPeriodToSeconds(periodType, periodValue);
  if (periodSeconds == null) return false;
  if (mode === COMPARE_MODE_OFFSET_HOURS) {
    return periodSeconds === amount * 3600;
  }
  if (mode === COMPARE_MODE_OFFSET_DAYS) {
    return periodSeconds === amount * 86400;
  }
  if (mode === COMPARE_MODE_BASELINE_DAYS) {
    if (periodSeconds % 86400 !== 0) return false;
    const days = periodSeconds / 86400;
    return days >= 1 && days <= amount;
  }
  if (mode === COMPARE_MODE_BASELINE_WEEKS) {
    const weekSeconds = 7 * 86400;
    if (periodSeconds % weekSeconds !== 0) return false;
    const weeks = periodSeconds / weekSeconds;
    return weeks >= 1 && weeks <= amount;
  }
  return false;
};

export const compareSpanIssue = ({
  mode,
  amount,
  periodType,
  periodValue,
  t
}: {
  mode?: string | null;
  amount?: number | null;
  periodType?: string | null;
  periodValue?: number | null;
  t: (
    key: string,
    defaultValue?: string,
    values?: Record<string, string | number>
  ) => string;
}): string | null => {
  const spec = compareSpanSpec(mode);
  if (!spec) return null;
  const label =
    mode === COMPARE_MODE_OFFSET_HOURS
      ? t('monitor.events.compareOffsetCountHour', '小时数')
      : mode === COMPARE_MODE_BASELINE_WEEKS
        ? t('monitor.events.compareOffsetCountWeek', '周数')
        : t('monitor.events.compareOffsetCountDay', '天数');
  if (amount == null || !Number.isFinite(amount)) {
    if (mode === COMPARE_MODE_OFFSET_HOURS) {
      return t('monitor.events.compareOffsetHoursRequired', '请填写对照小时数');
    }
    if (mode === COMPARE_MODE_BASELINE_WEEKS) {
      return t('monitor.events.compareBaselineWeeksRequired', '请填写对照周数');
    }
    return t('monitor.events.compareOffsetDaysRequired', '请填写对照天数');
  }
  const whole = Math.trunc(amount);
  if (whole !== amount || whole < 1) {
    return t(
      'monitor.events.compareSpanPositive',
      '{label}必须是正整数',
      { label }
    );
  }
  if (whole < spec.min) {
    return t('monitor.events.compareSpanAtLeast', '{label}至少为 {min}', {
      label,
      min: spec.min
    });
  }
  if (whole > spec.max) {
    return t('monitor.events.compareSpanAtMost', '{label}不能超过 {max}', {
      label,
      max: spec.max
    });
  }
  if (compareSpanConflict(mode, whole, periodType, periodValue)) {
    return t(
      'monitor.events.compareModeDisabledPeriod',
      '对照窗不能等于汇聚周期'
    );
  }
  return null;
};

export const COMPARE_RESULT_FAMILY_METRIC = 'metric';
export const COMPARE_RESULT_FAMILY_PERCENT = 'percent';
export const COMPARE_RESULT_FAMILY_RATIO = 'ratio';
export const COMPARE_RESULT_FAMILY_HOURS = 'hours';

export const compareResultFamily = (
  mode?: string | null,
  kind?: string | null
): string => {
  if (mode === COMPARE_MODE_TIMELEFT || kind === COMPARE_VALUE_KIND_HOURS) {
    return COMPARE_RESULT_FAMILY_HOURS;
  }
  if (kind === COMPARE_VALUE_KIND_PERCENT) {
    return COMPARE_RESULT_FAMILY_PERCENT;
  }
  if (kind === COMPARE_VALUE_KIND_RATIO) {
    return COMPARE_RESULT_FAMILY_RATIO;
  }
  return COMPARE_RESULT_FAMILY_METRIC;
};

export const clearThresholdNumbers = <T extends { value?: number | null }>(
  thresholds: T[]
): T[] => thresholds.map((item) => ({ ...item, value: null }));

export const TIMELEFT_PREVIEW_SPAN_CAP_HOURS = 720;

export const partitionTimeleftPreviewSeries = <
  T extends { values?: Array<[number, string] | number[]> }
>(
    series: T[],
    thresholdValues: Array<number | null | undefined>
  ): { kept: T[]; omitted: number } => {
  const finiteThresholds = thresholdValues.filter(
    (value): value is number =>
      typeof value === 'number' && Number.isFinite(value)
  );
  const maxThreshold = finiteThresholds.length
    ? Math.max(...finiteThresholds)
    : 0;
  const cap = Math.max(maxThreshold * 20, TIMELEFT_PREVIEW_SPAN_CAP_HOURS);
  const kept: T[] = [];
  let omitted = 0;
  series.forEach((item) => {
    const numbers = (item.values || [])
      .map((pair) => parseFloat(String(pair[1])))
      .filter((value) => Number.isFinite(value));
    const maxValue = numbers.length ? Math.max(...numbers) : 0;
    if (maxValue > cap) {
      omitted += 1;
    } else {
      kept.push(item);
    }
  });
  return { kept, omitted };
};

export const parseMetricInstanceValues = (raw?: string | null): string[] => {
  if (!raw) return [];
  const text = raw.trim();
  if (!text.startsWith('(') || !text.endsWith(')')) return [];
  const body = text.slice(1, -1);
  const values: string[] = [];
  let index = 0;
  while (index < body.length) {
    while (body[index] === ' ' || body[index] === ',') index += 1;
    if (index >= body.length) break;
    const quote = body[index];
    if (quote !== "'" && quote !== '"') return [];
    index += 1;
    let value = '';
    while (index < body.length) {
      if (body[index] === '\\' && index + 1 < body.length) {
        value += body[index + 1];
        index += 2;
        continue;
      }
      if (body[index] === quote) {
        index += 1;
        break;
      }
      value += body[index];
      index += 1;
    }
    values.push(value);
  }
  return values;
};

export const formatDryRunDimensionLabel = (
  metricInstanceId: string | undefined,
  dimensions: Array<{ name?: string; description?: string }> | undefined
): string => {
  const values = parseMetricInstanceValues(metricInstanceId);
  if (values.length <= 1) return '';
  return values
    .slice(1)
    .map((value, index) => {
      const dimension = dimensions?.[index + 1];
      const label = dimension?.description?.trim() || dimension?.name?.trim() || '';
      return label ? `${label}: ${value}` : value;
    })
    .join('-');
};

export const resolveLoadedCompareOffset = ({
  mode,
  hours,
  days,
  weeks
}: {
  mode?: string | null;
  hours?: number | null;
  days?: number | null;
  weeks?: number | null;
}): { mode: string; amount: number } => {
  if (mode === COMPARE_MODE_OFFSET_1H) {
    return { mode: COMPARE_MODE_OFFSET_HOURS, amount: 1 };
  }
  if (mode === COMPARE_MODE_OFFSET_24H) {
    return { mode: COMPARE_MODE_OFFSET_HOURS, amount: 24 };
  }
  if (mode === COMPARE_MODE_OFFSET_7D) {
    return { mode: COMPARE_MODE_OFFSET_DAYS, amount: 7 };
  }
  if (mode === COMPARE_MODE_OFFSET_30D) {
    return { mode: COMPARE_MODE_OFFSET_DAYS, amount: 30 };
  }
  if (mode === COMPARE_MODE_BASELINE_4W) {
    return { mode: COMPARE_MODE_BASELINE_WEEKS, amount: 4 };
  }
  if (mode === COMPARE_MODE_OFFSET_HOURS) {
    return {
      mode: COMPARE_MODE_OFFSET_HOURS,
      amount: normalizeCompareSpan(hours, 1)
    };
  }
  if (mode === COMPARE_MODE_OFFSET_DAYS) {
    return {
      mode: COMPARE_MODE_OFFSET_DAYS,
      amount: normalizeCompareSpan(days, 7)
    };
  }
  if (mode === COMPARE_MODE_BASELINE_DAYS) {
    return {
      mode: COMPARE_MODE_BASELINE_DAYS,
      amount: normalizeCompareSpan(days, 7)
    };
  }
  if (mode === COMPARE_MODE_BASELINE_WEEKS) {
    return {
      mode: COMPARE_MODE_BASELINE_WEEKS,
      amount: normalizeCompareSpan(weeks, 4)
    };
  }
  return { mode: mode || COMPARE_MODE_ABSOLUTE, amount: 1 };
};

export const isCompareModeAvailable = (
  mode: string,
  periodType?: string | null,
  periodValue?: number | null
): boolean => {
  const offsetSeconds = COMPARE_OFFSET_SECONDS[mode];
  if (!offsetSeconds) return true;
  const periodSeconds = policyPeriodToSeconds(periodType, periodValue);
  if (periodSeconds == null) return true;
  return periodSeconds !== offsetSeconds;
};

export const HIGH_SIDE_THRESHOLD_METHODS = new Set(['>', '>=']);

export const isHighSideThresholdMethod = (method?: string | null): boolean =>
  HIGH_SIDE_THRESHOLD_METHODS.has(method || '');

export const isLowSideThresholdMethod = (method?: string | null): boolean =>
  LOW_SIDE_THRESHOLD_METHODS.has(method || '');

export const getEnabledCompareModes = ({
  periodType,
  periodValue,
  algorithm
}: {
  periodType?: string | null;
  periodValue?: number | null;
  algorithm?: string | null;
}): string[] =>
  getCompareModeSelectOptions({ periodType, periodValue, algorithm })
    .filter((item) => !item.disabled)
    .map((item) => item.value);

export interface CompareModeSelectOption {
  value: string;
  disabled: boolean;
  reasonKey?: string;
}

export const getCompareModeSelectOptions = ({
  periodType,
  periodValue,
  algorithm
}: {
  periodType?: string | null;
  periodValue?: number | null;
  algorithm?: string | null;
}): CompareModeSelectOption[] => {
  const countIfLocked = algorithm === COUNT_IF_ALGORITHM;
  return ENABLED_COMPARE_MODES.map((mode) => {
    const periodBlocked = !isCompareModeAvailable(mode, periodType, periodValue);
    const countIfBlocked = countIfLocked && mode !== COMPARE_MODE_ABSOLUTE;
    const timeleftBlocked =
      mode === COMPARE_MODE_TIMELEFT &&
      !!algorithm &&
      !LEVEL_ALGORITHMS.includes(algorithm);
    const disabled = periodBlocked || countIfBlocked || timeleftBlocked;
    let reasonKey: string | undefined;
    if (countIfBlocked) {
      reasonKey = 'monitor.events.compareModeDisabledCountIf';
    } else if (periodBlocked) {
      reasonKey = 'monitor.events.compareModeDisabledPeriod';
    } else if (timeleftBlocked) {
      reasonKey = 'monitor.events.compareModeDisabledTimeleft';
    }
    return {
      value: mode,
      disabled,
      reasonKey
    };
  });
};

export const getAlgorithmGroupKey = (
  value: string | null | undefined
): 'window' | 'change' =>
  PER_SERIES_ALGORITHMS.includes(String(value || '')) ? 'change' : 'window';

export const groupAlgorithmOptions = <T extends { value?: string | number }>(
  items: T[]
): Array<{ key: 'window' | 'change'; options: T[] }> => {
  const windowOptions: T[] = [];
  const changeOptions: T[] = [];
  items.forEach((item) => {
    if (getAlgorithmGroupKey(String(item.value)) === 'change') {
      changeOptions.push(item);
    } else {
      windowOptions.push(item);
    }
  });
  return [
    windowOptions.length
      ? { key: 'window' as const, options: windowOptions }
      : null,
    changeOptions.length
      ? { key: 'change' as const, options: changeOptions }
      : null
  ].filter((group): group is { key: 'window' | 'change'; options: T[] } =>
    Boolean(group)
  );
};

export const coerceThresholdsForCompareMode = <
  T extends { method?: string | null }
>(
    compareMode: string,
    thresholds: T[]
  ): T[] => {
  if (compareMode !== COMPARE_MODE_TIMELEFT) {
    return thresholds;
  }
  return thresholds.map((item) => {
    if (item.method === '>') {
      return { ...item, method: '<' };
    }
    if (item.method === '>=') {
      return { ...item, method: '<=' };
    }
    return item;
  });
};

export const recoveryConflictsWithThresholds = (
  recovery: { method?: string | null } | null | undefined,
  thresholds: Array<{ method?: string | null }> | null | undefined
): boolean => {
  const recoveryMethod = recovery?.method;
  if (!recoveryMethod) {
    return false;
  }
  const triggerMethods = (thresholds || [])
    .map((item) => item.method)
    .filter((method): method is string => !!method);
  if (!triggerMethods.length) {
    return false;
  }
  const sides = new Set(
    triggerMethods.map((method) =>
      isHighSideThresholdMethod(method)
        ? 'high'
        : isLowSideThresholdMethod(method)
          ? 'low'
          : 'other'
    )
  );
  if (sides.has('other') || sides.size > 1) {
    return true;
  }
  if (sides.has('high')) {
    return isHighSideThresholdMethod(recoveryMethod);
  }
  return isLowSideThresholdMethod(recoveryMethod);
};

export const coerceRecoveryForThresholds = <
  T extends { method?: string; value?: number | null }
>(
    recovery: T | null | undefined,
    thresholds: Array<{ method?: string | null }> | null | undefined
  ): T | { method: string; value: null } => {
  if (recoveryConflictsWithThresholds(recovery, thresholds)) {
    return { method: '', value: null };
  }
  return recovery || { method: '', value: null };
};

export const getAllowedThresholdMethods = <T extends { value?: string | number }>(
  compareMode: string,
  allMethods: T[]
): T[] => {
  if (compareMode !== COMPARE_MODE_TIMELEFT) {
    return allMethods;
  }
  return allMethods.filter((item) =>
    isLowSideThresholdMethod(String(item.value || ''))
  );
};

export const getAllowedRecoveryMethods = <T extends { value?: string | number }>(
  thresholds: Array<{ method?: string | null }> | null | undefined,
  allMethods: T[]
): T[] => {
  const triggerMethods = (thresholds || [])
    .map((item) => item.method)
    .filter((method): method is string => !!method);
  if (!triggerMethods.length) {
    return allMethods;
  }
  const allHigh = triggerMethods.every((method) =>
    isHighSideThresholdMethod(method)
  );
  const allLow = triggerMethods.every((method) =>
    isLowSideThresholdMethod(method)
  );
  if (allHigh) {
    return allMethods.filter((item) =>
      isLowSideThresholdMethod(String(item.value || ''))
    );
  }
  if (allLow) {
    return allMethods.filter((item) =>
      isHighSideThresholdMethod(String(item.value || ''))
    );
  }
  return [];
};

type TranslateFn = (
  key: string,
  defaultValue?: string,
  values?: Record<string, string | number>
) => string;

export const buildPolicyRestatement = ({
  t,
  metricLabel,
  algorithmLabel,
  algorithm,
  compareMode,
  compareValueKind,
  compareModeLabel,
  thresholdMethod,
  thresholdValue,
  thresholdUnitLabel,
  countPredicateMethod,
  countPredicateValue,
  forecastTarget,
  compareOffsetHours
}: {
  t: TranslateFn;
  metricLabel?: string | null;
  algorithmLabel?: string | null;
  algorithm?: string | null;
  compareMode?: string | null;
  compareValueKind?: string | null;
  compareModeLabel?: string | null;
  thresholdMethod?: string | null;
  thresholdValue?: number | null;
  thresholdUnitLabel?: string | null;
  countPredicateMethod?: string | null;
  countPredicateValue?: number | null;
  forecastTarget?: number | null;
  compareOffsetHours?: number | null;
}): string => {
  const metric =
    metricLabel?.trim() ||
    t('monitor.events.policyRestatementMetricFallback', '所选指标');
  const algo = algorithmLabel?.trim() || '';
  const method = thresholdMethod || '';
  const valueText =
    thresholdValue == null || !Number.isFinite(Number(thresholdValue))
      ? '…'
      : String(thresholdValue);
  const unit = thresholdUnitLabel || '';
  const valueWithUnit = `${valueText}${unit ? ` ${unit}` : ''}`.trim();

  if (algorithm === COUNT_IF_ALGORITHM) {
    const innerValue =
      countPredicateValue == null ||
      !Number.isFinite(Number(countPredicateValue))
        ? '…'
        : String(countPredicateValue);
    const inner = `${countPredicateMethod || ''} ${innerValue}`.trim();
    return t(
      'monitor.events.policyRestatementCountIf',
      '这条策略在判断：窗口内满足 {inner} 的点数 {method} {value}。',
      { inner, method, value: valueWithUnit }
    );
  }

  if (compareMode === COMPARE_MODE_TIMELEFT) {
    const direction =
      thresholdMethod === '<='
        ? t('monitor.events.policyRestatementAtMost', '不超过')
        : t('monitor.events.policyRestatementUnder', '不足');
    if (forecastTarget == null) {
      return t(
        'monitor.events.policyRestatementTimeleftNeedTarget',
        '这条策略在判断：{metric}距容量线还剩{direction} {value} 小时（请填写容量线）。',
        { metric, direction, value: valueText }
      );
    }
    return t(
      'monitor.events.policyRestatementTimeleft',
      '这条策略在判断：{metric}距容量线还剩{direction} {value} 小时。',
      { metric, direction, value: valueText }
    );
  }

  if (!compareMode || compareMode === COMPARE_MODE_ABSOLUTE) {
    return t(
      'monitor.events.policyRestatementAbsolute',
      '这条策略在判断：{metric}的{algorithm} {method} {value}。',
      { metric, algorithm: algo, method, value: valueWithUnit }
    );
  }

  const direction = isHighSideThresholdMethod(thresholdMethod)
    ? t('monitor.events.policyRestatementHigh', '高出')
    : isLowSideThresholdMethod(thresholdMethod)
      ? t('monitor.events.policyRestatementLow', '低出')
      : t('monitor.events.policyRestatementDiff', '相差');
  const percentPointLabel = unit.trim().toLowerCase();
  const isPercentPoint =
    percentPointLabel === '%' ||
    percentPointLabel === '％' ||
    percentPointLabel.startsWith('percent');
  let compared = valueWithUnit;
  if (compareValueKind === COMPARE_VALUE_KIND_PERCENT) {
    compared = `${valueText}%`;
  } else if (
    compareValueKind === COMPARE_VALUE_KIND_DELTA &&
    isPercentPoint
  ) {
    compared = t(
      'monitor.events.policyRestatementPercentPoints',
      '{value} 个百分点',
      { value: valueText }
    );
  } else if (compareValueKind === COMPARE_VALUE_KIND_RATIO) {
    compared = t(
      'monitor.events.policyRestatementRatioValue',
      '{value} 倍',
      { value: valueText }
    );
  }
  const baselineKey = compareMode
    ? COMPARE_RESTATEMENT_BASELINE_KEYS[compareMode]
    : undefined;
  const spanText =
    compareOffsetHours != null && Number.isFinite(compareOffsetHours)
      ? compareOffsetHours
      : '…';
  const baseline =
    compareMode === COMPARE_MODE_OFFSET_HOURS
      ? t('monitor.events.compareModeOffsetHoursRestate', '{n} 小时前', {
        n: spanText
      })
      : compareMode === COMPARE_MODE_OFFSET_DAYS
        ? t('monitor.events.compareModeOffsetDaysRestate', '{n} 天前', {
          n: spanText
        })
        : compareMode === COMPARE_MODE_BASELINE_DAYS
          ? t(
            'monitor.events.compareModeBaselineDaysRestate',
            '近 {n} 天同窗均值',
            { n: spanText }
          )
          : compareMode === COMPARE_MODE_BASELINE_WEEKS
            ? t(
              'monitor.events.compareModeBaselineWeeksRestate',
              '近 {n} 周同窗均值',
              { n: spanText }
            )
            : baselineKey
              ? t(baselineKey.key, baselineKey.fallback)
              : compareModeLabel || '';
  return t(
    'monitor.events.policyRestatementCompare',
    '这条策略在判断：{metric}的{algorithm}，比 {baseline}{direction} {value}。',
    {
      metric,
      algorithm: algo,
      baseline,
      direction,
      value: compared
    }
  );
};

export const getCompareValueKinds = (mode: string): string[] =>
  (COMPARE_VALUE_KINDS_BY_MODE[mode] || ['']).filter(Boolean);

export const defaultCompareValueKind = (mode: string): string =>
  getCompareValueKinds(mode)[0] || '';

export const resolveCompareFieldsForSave = ({
  isTrap,
  compareMode,
  compareValueKind,
  algorithm,
  countPredicate,
  forecastTarget,
  forecastTargetUnit,
  forecastLookback,
  compareOffsetHours
}: {
  isTrap: boolean;
  compareMode?: string | null;
  compareValueKind?: string | null;
  algorithm?: string | null;
  countPredicate?: { method?: string; value?: number | null } | null;
  forecastTarget?: number | null;
  forecastTargetUnit?: string | null;
  forecastLookback?: { type: string; value: number } | null;
  compareOffsetHours?: number | null;
}): {
  compare_mode: string;
  compare_value_kind: string;
  count_predicate: Record<string, unknown>;
  forecast_target: number | null;
  forecast_target_unit: string;
  forecast_lookback: Record<string, unknown>;
  compare_offset_hours: number | null;
  compare_offset_days: number | null;
  compare_baseline_weeks: number | null;
} => {
  if (isTrap) {
    return {
      compare_mode: COMPARE_MODE_ABSOLUTE,
      compare_value_kind: '',
      count_predicate: {},
      forecast_target: null,
      forecast_target_unit: '',
      forecast_lookback: {},
      compare_offset_hours: null,
      compare_offset_days: null,
      compare_baseline_weeks: null
    };
  }
  const mode = compareMode || COMPARE_MODE_ABSOLUTE;
  const spanSpec = compareSpanSpec(mode);
  const span =
    spanSpec &&
    compareOffsetHours != null &&
    Number.isFinite(compareOffsetHours) &&
    compareOffsetHours >= 1
      ? Math.min(
        spanSpec.max,
        Math.max(spanSpec.min, Math.floor(compareOffsetHours))
      )
      : null;
  if (mode === COMPARE_MODE_ABSOLUTE) {
    return {
      compare_mode: COMPARE_MODE_ABSOLUTE,
      compare_value_kind: '',
      count_predicate:
        algorithm === COUNT_IF_ALGORITHM && countPredicate?.method
          ? {
            method: countPredicate.method,
            value: countPredicate.value
          }
          : {},
      forecast_target: null,
      forecast_target_unit: '',
      forecast_lookback: {},
      compare_offset_hours: null,
      compare_offset_days: null,
      compare_baseline_weeks: null
    };
  }
  const allowed = getCompareValueKinds(mode);
  const kind =
    compareValueKind && allowed.includes(compareValueKind)
      ? compareValueKind
      : defaultCompareValueKind(mode);
  return {
    compare_mode: mode,
    compare_value_kind: kind,
    count_predicate: {},
    forecast_target:
      mode === COMPARE_MODE_TIMELEFT ? forecastTarget ?? null : null,
    forecast_target_unit:
      mode === COMPARE_MODE_TIMELEFT ? forecastTargetUnit || '' : '',
    forecast_lookback:
      mode === COMPARE_MODE_TIMELEFT
        ? forecastLookback || DEFAULT_FORECAST_LOOKBACK
        : {},
    compare_offset_hours: mode === COMPARE_MODE_OFFSET_HOURS ? span : null,
    compare_offset_days:
      mode === COMPARE_MODE_OFFSET_DAYS || mode === COMPARE_MODE_BASELINE_DAYS
        ? span
        : null,
    compare_baseline_weeks: mode === COMPARE_MODE_BASELINE_WEEKS ? span : null
  };
};

export const resolveRecoveryThresholdForSave = ({
  isTrap,
  recoveryThreshold
}: {
  isTrap: boolean;
  recoveryThreshold?: { method?: string; value?: number | null } | null;
}): Record<string, unknown> => {
  if (isTrap) return {};
  const method = recoveryThreshold?.method;
  const value = recoveryThreshold?.value;
  if (!method || value == null || !Number.isFinite(value)) {
    return {};
  }
  return { method, value };
};

export const resolveNoDataPeriodsForSave = ({
  enabled,
  detectionValue,
  detectionUnit,
  recoveryValue,
  recoveryUnit
}: {
  enabled: boolean;
  detectionValue: number | null;
  detectionUnit: string;
  recoveryValue: number | null;
  recoveryUnit: string;
}): {
  no_data_period: Record<string, unknown> | { type: string; value: number };
  no_data_recovery_period: Record<string, unknown> | { type: string; value: number };
} => {
  if (!enabled) {
    const periodValue = detectionValue
      ? { type: detectionUnit, value: detectionValue }
      : {};
    return {
      no_data_period: periodValue,
      no_data_recovery_period: periodValue
    };
  }
  const detection = {
    type: detectionUnit,
    value: detectionValue
  };
  return {
    no_data_period: detection,
    no_data_recovery_period: {
      type: recoveryUnit || detectionUnit,
      value: recoveryValue ?? detectionValue
    }
  };
};

export const mapQuantityToRateUnit = (
  unit?: string | null
): string | null => {
  const raw = (unit || '').trim();
  if (!raw) return raw || null;
  const normalized = raw.toLowerCase();
  if (ALREADY_PER_SECOND_UNITS.has(normalized)) {
    return normalized;
  }
  return QUANTITY_TO_RATE_UNIT[normalized] || raw;
};

export const shouldAnnotatePerSecond = (
  unit?: string | null,
  algorithm?: string | null
): boolean => {
  if (algorithm !== 'rate' && algorithm !== 'deriv') {
    return false;
  }
  const normalized = (unit || '').trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  if (ALREADY_PER_SECOND_UNITS.has(normalized)) {
    return false;
  }
  return !QUANTITY_TO_RATE_UNIT[normalized];
};

export const formatUnitLabelWithRateSuffix = (
  label: string,
  unit?: string | null,
  algorithm?: string | null
): string => {
  const text = label || '';
  if (!shouldAnnotatePerSecond(unit, algorithm)) {
    return text;
  }
  if (!text) {
    return '/s';
  }
  if (/\/s$/i.test(text)) {
    return text;
  }
  return `${text}/s`;
};

export const resolvePolicyResultUnit = ({
  compareValueKind,
  calculationUnit,
  metricUnit,
  algorithm
}: {
  compareValueKind?: string | null;
  calculationUnit?: string | null;
  metricUnit?: string | null;
  algorithm?: string | null;
}): { unit: string | null; conversionEnabled: boolean } => {
  if (compareValueKind === COMPARE_VALUE_KIND_PERCENT) {
    return { unit: 'percent', conversionEnabled: false };
  }
  if (compareValueKind === COMPARE_VALUE_KIND_RATIO) {
    return { unit: null, conversionEnabled: false };
  }
  if (compareValueKind === COMPARE_VALUE_KIND_HOURS) {
    return { unit: 'hour', conversionEnabled: false };
  }
  if (algorithm === 'changes' || algorithm === COUNT_IF_ALGORITHM) {
    return { unit: 'count', conversionEnabled: false };
  }
  if (algorithm === 'rate' || algorithm === 'deriv') {
    return {
      unit: mapQuantityToRateUnit(metricUnit || calculationUnit),
      conversionEnabled: false
    };
  }
  return {
    unit: calculationUnit || null,
    conversionEnabled: true
  };
};

export const resolveThresholdUnitBase = ({
  compareValueKind,
  calculationUnit,
  metricUnit,
  algorithm
}: {
  compareValueKind?: string | null;
  calculationUnit?: string | null;
  metricUnit?: string | null;
  algorithm?: string | null;
}): string | null => {
  const result = resolvePolicyResultUnit({
    compareValueKind,
    calculationUnit,
    metricUnit,
    algorithm
  });
  return result.conversionEnabled ? calculationUnit || null : result.unit;
};

export const shouldDrawPreviewThreshold = ({
  overlay,
  compareValueKind
}: {
  overlay?: boolean;
  compareValueKind?: string | null;
} = {}): boolean => {
  if (!overlay) {
    return true;
  }
  return (
    compareValueKind !== COMPARE_VALUE_KIND_PERCENT &&
    compareValueKind !== COMPARE_VALUE_KIND_RATIO
  );
};

export const buildMetricSelectOption = (
  metric: MetricItem,
  unitList: UnitListItem[]
): { label: string; value: string } => {
  const displayName = metric.display_name || metric.name;
  const displayUnit = resolveMetricDisplayUnit(metric.unit, unitList);
  return {
    label: displayUnit ? `${displayName}（${displayUnit}）` : displayName,
    value: metric.name
  };
};

// 现有 page.tsx 的 filterInvalidUnit 逻辑上提到 utils(行为完全一致,签名兼容)
export const filterInvalidCalculationUnit = (
  unit: string | null | undefined
): string | null => {
  if (isVacantThresholdUnit(unit) || isStringArray(unit || '')) {
    return null;
  }
  return unit ?? null;
};

/**
 * 指标切换时解析 calculation/threshold 单位。
 * none/short/枚举/空 → null，禁止再按 system===null 回落到 cps 等独立单位。
 */
export const resolveUnitOnMetricSelect = (
  metricUnit: string | null | undefined
): string | null => filterInvalidCalculationUnit(metricUnit);

export const restoreCalculationUnitState = (
  unit: string | null | undefined
): string | null => filterInvalidCalculationUnit(unit);

export const resolveEffectiveCalculationUnit = ({
  isFormulaMode,
  unit,
  unitList
}: {
  isFormulaMode: boolean;
  unit: string | null | undefined;
  unitList: UnitListItem[];
}): string | null => {
  if (isFormulaMode) {
    return resolveFormulaResultUnit(unit, unitList);
  }

  const normalizedUnit = filterInvalidCalculationUnit(unit);
  if (!normalizedUnit) return null;

  return getValidThresholdUnitOptions(unitList).some(
    (item) => item.unit_id === normalizedUnit
  )
    ? normalizedUnit
    : null;
};

/** 将告警名称变量插入光标/选区位置；未提供选区时追加到末尾 */
export const insertAlertNameVariableAtCursor = (
  text: string,
  variable: string,
  selectionStart?: number | null,
  selectionEnd?: number | null
): { value: string; cursor: number } => {
  const fallback = text.length;
  const rawStart =
    typeof selectionStart === 'number' ? selectionStart : fallback;
  const rawEnd = typeof selectionEnd === 'number' ? selectionEnd : rawStart;
  const start = Math.max(0, Math.min(rawStart, text.length));
  const end = Math.max(start, Math.min(rawEnd, text.length));
  return {
    value: `${text.slice(0, start)}${variable}${text.slice(end)}`,
    cursor: start + variable.length
  };
};

// 公式 → 单指标 retract:返回新值;否则返回 undefined 表示「无变化」
export const getReverseModeCalculationUnit = ({
  previousMode,
  nextMode,
  primaryMetricUnit,
}: {
  previousMode: MetricExpressionMode;
  nextMode: MetricExpressionMode;
  primaryMetricUnit: string | null | undefined;
}): string | null | undefined => {
  if (previousMode === 'formula' && nextMode !== 'formula') {
    return filterInvalidCalculationUnit(primaryMetricUnit);
  }
  return undefined;
};

export const METRIC_DIMENSION_VARIABLE_PREFIX = 'metric__';

export const buildMetricDimensionVariable = (dimension: string) =>
  `\${${METRIC_DIMENSION_VARIABLE_PREFIX}${dimension}}`;

/** 所选分组维度渲染为后端可替换的 ${metric__key} 名称变量。 */
export const buildMetricDimensionVariables = (groupBy?: string[] | null) => {
  const seen = new Set<string>();
  const items: Array<{ key: string; variable: string; dimension: string }> = [];
  for (const raw of groupBy || []) {
    const dimension = String(raw || '').trim();
    if (!dimension || seen.has(dimension)) continue;
    seen.add(dimension);
    items.push({
      key: `${METRIC_DIMENSION_VARIABLE_PREFIX}${dimension}`,
      variable: buildMetricDimensionVariable(dimension),
      dimension
    });
  }
  return items;
};

const RANGE_DURATION_RE =
  /\[(?:__\$window__|(\d+(?:\.\d+)?)(ms|s|m|h|d|w|y))(?::[^\]]*)?\]/gi;

const DURATION_MINUTES: Record<string, number> = {
  ms: 1 / 60000,
  s: 1 / 60,
  m: 1,
  h: 60,
  d: 1440,
  w: 10080,
  y: 525600
};

export const scheduleValueToMinutes = (
  value: number | null | undefined,
  unit: string | null | undefined
): number => {
  if (value == null || !Number.isFinite(value) || value <= 0) {
    return 0;
  }
  if (unit === 'hour') {
    return value * 60;
  }
  if (unit === 'day') {
    return value * 1440;
  }
  if (unit === 's' || unit === 'sec') {
    return value / 60;
  }
  return value;
};

const durationToMinutes = (value: number, unit: string): number => {
  const factor = DURATION_MINUTES[unit.toLowerCase()];
  if (!factor) {
    return 0;
  }
  return value * factor;
};

export const collectMetricQueryTexts = ({
  rows,
  metrics,
  formulaExpression
}: {
  rows: Array<{ metricId?: number | null; metricName?: string }>;
  metrics: MetricItem[];
  formulaExpression?: string;
}): string[] => {
  const queries: string[] = [];
  rows.forEach((row) => {
    const metric = metrics.find(
      (item) =>
        (row.metricId != null && String(item.id) === String(row.metricId)) ||
        (!!row.metricName && item.name === row.metricName)
    );
    if (metric?.query) {
      queries.push(metric.query);
    }
  });
  if (formulaExpression?.trim()) {
    queries.push(formulaExpression);
  }
  return queries;
};

export const baseQueryContainsRateFunction = (
  query?: string | null
): boolean => RATE_FUNCTION_RE.test(query || '');

export const queriesContainRateFunction = (queries: string[]): boolean =>
  queries.some((query) => baseQueryContainsRateFunction(query));

export const rateAlgorithmConflictsWithQuery = (
  algorithm: string | null | undefined,
  queries: string[]
): boolean => algorithm === 'rate' && queriesContainRateFunction(queries);

export const resolveFunctionDelayMinutes = (
  queries: string[],
  windowMinutes = 0
): number | null => {
  let maxMinutes = 0;
  queries.forEach((query) => {
    if (!query) {
      return;
    }
    RANGE_DURATION_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = RANGE_DURATION_RE.exec(query)) !== null) {
      if (match[1] == null) {
        maxMinutes = Math.max(maxMinutes, windowMinutes);
        continue;
      }
      maxMinutes = Math.max(
        maxMinutes,
        durationToMinutes(Number(match[1]), match[2])
      );
    }
  });
  if (maxMinutes <= 0) {
    return null;
  }
  return Math.max(1, Math.ceil(maxMinutes));
};

export const DRY_RUN_VERDICT_I18N: Record<string, string> = {
  would_trigger: 'monitor.events.dryRunVerdictWouldTrigger',
  ok: 'monitor.events.dryRunVerdictOk',
  would_recover: 'monitor.events.dryRunVerdictWouldRecover',
  no_data: 'monitor.events.dryRunVerdictNoData',
  missing_baseline: 'monitor.events.dryRunVerdictMissingBaseline',
  insufficient_samples: 'monitor.events.dryRunVerdictInsufficientSamples',
  hold: 'monitor.events.dryRunVerdictHold',
};

export const formatDryRunHitCountCopy = (
  hitCount: number,
  triggerCount: number
): string | null => {
  if (!triggerCount || triggerCount <= 1) return null;
  if (hitCount >= triggerCount) return null;
  return `本轮命中 ${hitCount}/${triggerCount}，现网不会建告警`;
};

export const resolveDryRunReason = (item: {
  verdict?: string;
  reason?: string | null;
  hit_count?: number | null;
  trigger_count?: number | null;
}): string => {
  const reason = typeof item.reason === 'string' ? item.reason.trim() : '';
  return reason;
};

export const formatDryRunNumber = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return String(Number(number.toFixed(4)));
};

export const formatDryRunThreshold = (
  threshold:
    | {
        method?: string;
        value?: number | string | null;
        level?: string;
      }
    | null
    | undefined
): string => {
  if (!threshold) return '—';
  const method = threshold.method || '';
  const value = formatDryRunNumber(threshold.value);
  const level = threshold.level ? ` ${threshold.level}` : '';
  if (!method && value === '—') return '—';
  return `${method} ${value}${level}`.trim();
};
