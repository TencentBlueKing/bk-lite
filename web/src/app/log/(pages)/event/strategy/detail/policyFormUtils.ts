import type React from 'react';
import { FUNCTION_LIST } from '@/app/log/constants';
import { FilterItem } from '@/app/log/types/integration';
import { ChannelItem, StrategyFields } from '@/app/log/types/event';
import { compareOffsetReady, presentCompare } from '@/app/log/utils/compareTarget';

export const conditionRequiresField = (func?: string | null) => {
  if (func === 'count_delta' || func === 'count_rate' || func === 'bytes_rate' || func === 'ratio') {
    return false;
  }
  const option = FUNCTION_LIST.find((item) => item.value === func);
  return option ? option.needsField : true;
};

/** 读入旧策略时，count_delta 显示为计数 + 变化量 + 上一窗。 */
export const normalizeCondition = (condition: FilterItem): FilterItem => {
  if (condition.func === 'count_delta') {
    return {
      ...condition,
      func: 'count',
      field: '_msg',
      compare: { kind: 'delta', to: 'previous_window' },
      params: condition.params || {},
    };
  }
  return {
    ...condition,
    compare: presentCompare(condition.compare),
    params: condition.params || {},
  };
};

/** 读入策略时回填连续满足次数。缺省 1。 */
export const readPolicyTriggerCount = (
  alertCondition?: StrategyFields['alert_condition']
): number => {
  const raw = alertCondition?.rule?.trigger_count;
  if (typeof raw !== 'number' || !Number.isInteger(raw) || raw < 1 || raw > 5) {
    return 1;
  }
  return raw;
};

/** 变化量 / 变化率要对照，分位要分位，占比要分子筛选。 */
export const hasIncompleteCondition = (conditions: FilterItem[]) =>
  conditions.some((item) => {
    if (!item.func || !item.op || item.value == null || String(item.value) === '') {
      return true;
    }
    if (conditionRequiresField(item.func) && !item.field) {
      return true;
    }
    const kind = item.compare?.kind || 'absolute';
    if ((kind === 'percent' || kind === 'delta') && !compareOffsetReady(item.compare)) {
      return true;
    }
    if (item.func === 'quantile' && item.params?.quantile == null) {
      return true;
    }
    if (item.func === 'ratio' && !String(item.params?.filter || '').trim()) {
      return true;
    }
    return false;
  });

const NUMERIC_ONLY_FUNCS = new Set(['count_rate', 'count_delta', 'count_uniq', 'quantile', 'ratio', 'bytes_rate']);
/** 与 PolicySerializer 一致：数值函数，或比较方式不是当前值时，阈值必须是有限数。 */
export const isNumericCompare = (func?: string | null, kind?: string | null) =>
  NUMERIC_ONLY_FUNCS.has(String(func)) || (kind || 'absolute') !== 'absolute';
/** 数值比较场景下阈值不是有限数。只在 hasIncompleteCondition 为 false 后调用。 */
export const hasNonNumericThreshold = (conditions: FilterItem[]) =>
  conditions.some((item) => {
    const kind = presentCompare(item.compare).kind || 'absolute';
    return isNumericCompare(item.func, kind) && !Number.isFinite(Number(item.value));
  });

export type LogPolicyType = 'keyword' | 'aggregate';

const POLICY_TYPES = new Set<LogPolicyType>(['keyword', 'aggregate']);
export const FIXED_SHOW_FIELDS = ['timestamp', 'message'] as const;
const DEFAULT_SHOW_FIELDS = [...FIXED_SHOW_FIELDS];

export const getLockedPolicyType = ({
  urlAlertType,
  detailAlertType
}: {
  urlAlertType?: string | null;
  detailAlertType?: string | null;
}): LogPolicyType => {
  if (POLICY_TYPES.has(detailAlertType as LogPolicyType)) {
    return detailAlertType as LogPolicyType;
  }
  if (POLICY_TYPES.has(urlAlertType as LogPolicyType)) {
    return urlAlertType as LogPolicyType;
  }
  return 'keyword';
};

export const getDefaultShowFields = (fields?: string[] | null): string[] => {
  const merged = [...DEFAULT_SHOW_FIELDS, ...(fields || [])].filter(Boolean);
  return Array.from(new Set(merged));
};

/** 与服务端 AlertConstants.MAX_BACKFILL_COUNT 一致：一轮最多补扫 10 个周期。 */
export const MAX_BACKFILL_COUNT = 10;
const UNIT_SECONDS: Record<string, number> = { min: 60, hour: 3600, day: 86400 };
export const toTimingSeconds = (value: unknown, unit: string) =>
  typeof value === 'number' && Number.isFinite(value) ? value * (UNIT_SECONDS[unit] || 0) : 0;
/** 频率超过周期 × 补扫上限时返回 true。 */
export const hasBackfillGap = (schedule: unknown, unit: string, period: unknown, periodUnit: string) => {
  const s = toTimingSeconds(schedule, unit);
  const p = toTimingSeconds(period, periodUnit);
  return s > 0 && p > 0 && s > MAX_BACKFILL_COUNT * p;
};

export const getAlertConditionVisibility = (policyType: LogPolicyType) => ({
  showDisplayFields: true,
  showGroupBy: true,
  showRule: policyType === 'aggregate'
});

export const buildLogFieldVariable = (field: string) =>
  field.startsWith('log.') ? '${' + field + '}' : '${log.' + field + '}';

const fieldToken = (field?: string | null) => (field || '_msg').replace(/\./g, '_');

/** 告警名称可替换的聚合键，与扫描写入 aggregate_result 的键一致。占比用条件在列表中的序号。 */
export const aggregateTemplateVariables = (conditions?: FilterItem[] | null) => {
  const values: string[] = [];
  const push = (value: string) => {
    if (value && !values.includes(value)) {
      values.push(value);
    }
  };
  (conditions || []).forEach((raw, index) => {
    if (!raw?.func) {
      return;
    }
    const condition = normalizeCondition(raw);
    const func = condition.func;
    const token = fieldToken(condition.field);
    if (func === 'count') {
      push('${count}');
    }
    if (func === 'count_rate') {
      push('${count_rate}');
    }
    if (func === 'bytes_rate') {
      push('${bytes_rate}');
    }
    if (func === 'count_uniq') {
      push('${count_uniq_' + token + '}');
    }
    if (func === 'quantile' && typeof condition.params?.quantile === 'number') {
      push('${quantile_' + String(condition.params.quantile).replace('.', '_') + '_' + token + '}');
    }
    if (func === 'ratio') {
      push('${ratio_' + index + '}');
    }
    const kind = condition.compare?.kind;
    const target = condition.compare?.to;
    if (!kind || kind === 'absolute' || !target) {
      return;
    }
    if (func === 'count' && kind === 'delta' && target === 'previous_window') {
      push('${count_delta}');
      push('${previous_count}');
    }
    let baselineKey = '';
    if (func === 'count') {
      baselineKey = 'count_' + token;
    } else if (func === 'count_uniq') {
      baselineKey = 'count_uniq_' + token;
    } else if (func === 'quantile' && typeof condition.params?.quantile === 'number') {
      baselineKey = 'quantile_' + String(condition.params.quantile).replace('.', '_') + '_' + token;
    } else if (func === 'sum' || func === 'avg' || func === 'max' || func === 'min') {
      baselineKey = func + '_' + token;
    }
    if (baselineKey) {
      push('${baseline_' + baselineKey + '}');
    }
  });
  return values;
};

export const buildAlertNameVariables = (
  groupBy?: string[] | null,
  conditions?: FilterItem[] | null
) => {
  const variableItems = new Map<
    string,
    { value: string; label: string; description: 'alertLevel' | 'groupField' | 'aggregateValue' }
  >();
  variableItems.set('${level}', {
    value: '${level}',
    label: '${level}',
    description: 'alertLevel'
  });
  (groupBy || []).filter(Boolean).forEach((field) => {
    const value = buildLogFieldVariable(field);
    variableItems.set(value, {
      value,
      label: value,
      description: 'groupField'
    });
  });
  aggregateTemplateVariables(conditions).forEach((value) => {
    variableItems.set(value, {
      value,
      label: value,
      description: 'aggregateValue'
    });
  });
  return Array.from(variableItems.values());
};

export const buildLogPreviewSearchParams = ({
  query,
  logGroups,
  now = new Date()
}: {
  query?: string;
  logGroups?: React.Key[];
  now?: Date;
}) => {
  const end = now.getTime();
  const start = end - 15 * 60 * 1000;
  return {
    query: query || '*',
    log_groups: logGroups || [],
    limit: 10,
    start_time: new Date(start).toISOString(),
    end_time: new Date(end).toISOString()
  };
};

export const shouldFetchLogPreview = ({
  query,
  logGroups
}: {
  query?: string;
  logGroups?: React.Key[];
}) => !!query?.trim() && !!logGroups?.length;

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

/** 邮件渠道从组织用户里选人，组织变更后需要裁掉越界通知人；标签渠道是自由文本，不能按用户列表裁 */
export const shouldPruneNoticeUsers = ({
  noticeTypeId,
  channelList
}: {
  noticeTypeId?: string | number;
  channelList: Array<{ id: string | number; channel_type: string }>;
}): boolean => {
  if (noticeTypeId == null || noticeTypeId === '') return false;
  const selected = channelList.find(
    (channel) => String(channel.id) === String(noticeTypeId)
  );
  return selected?.channel_type === 'email';
};

/** 开启通知且所选渠道需要通知人时，通知人必填 */
export const shouldRequireNoticeUsers = ({
  notice,
  noticeTypeId,
  channelList
}: {
  notice?: boolean;
  noticeTypeId?: string | number;
  channelList: Array<{ id: string | number; channel_type: string }>;
}): boolean => {
  if (!notice) return false;
  if (noticeTypeId == null || noticeTypeId === '') return false;
  const selected = channelList.find(
    (channel) => String(channel.id) === String(noticeTypeId)
  );
  if (!selected) return false;
  return selected.channel_type !== 'nats';
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

export const insertAlertNameVariable = (
  text: string,
  variable: string,
  selectionStart?: number | null,
  selectionEnd?: number | null
): string => {
  if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
    return `${text.slice(0, selectionStart)}${variable}${text.slice(selectionEnd)}`;
  }
  return `${text}${variable}`;
};

const normalizeTimingValue = (
  value: StrategyFields['schedule'] | StrategyFields['period'],
  unit: string
) => {
  if (value && typeof value === 'object') {
    return value;
  }
  return {
    type: unit,
    value: value as number
  };
};

export const buildStrategyPayload = (
  values: StrategyFields,
  options: {
    unit: string;
    periodUnit: string;
    channelList: ChannelItem[];
    conditions: FilterItem[];
    term: string | null;
    isEdit: boolean;
    formData?: StrategyFields;
  }
): StrategyFields => {
  const params: StrategyFields = {
    ...values,
    show_fields: getDefaultShowFields(values.show_fields),
    schedule: normalizeTimingValue(values.schedule, options.unit),
    period: normalizeTimingValue(values.period, options.periodUnit)
  };

  if (params.notice_type_id) {
    params.notice_type =
      options.channelList.find((item) => item.id === params.notice_type_id)
        ?.channel_type || '';
  }

  const groupBy = Array.isArray(values.group_by) ? values.group_by : [];
  params.alert_condition = {
    query: values.query || '',
    group_by: groupBy
  };

  if (params.alert_type === 'aggregate') {
    params.alert_condition.rule = {
      mode: options.term || 'and',
      conditions: options.conditions
    };
  }
  if (typeof values.trigger_count === 'number') {
    const rule = params.alert_condition.rule;
    params.alert_condition.rule = {
      mode: rule?.mode || options.term || 'and',
      conditions: rule?.conditions || [],
      trigger_count: values.trigger_count
    };
  }
  if (options.isEdit) {
    params.id = options.formData?.id;
  } else {
    params.enable = true;
  }

  return params;
};
