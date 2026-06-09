import { FilterItem } from '@/app/log/types/integration';
import { ChannelItem, StrategyFields } from '@/app/log/types/event';

export type LogPolicyType = 'keyword' | 'aggregate';

const POLICY_TYPES = new Set<LogPolicyType>(['keyword', 'aggregate']);
const DEFAULT_SHOW_FIELDS = ['timestamp', 'message'];

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

export const getAlertConditionVisibility = (policyType: LogPolicyType) => ({
  showDisplayFields: true,
  showGroupBy: true,
  showRule: policyType === 'aggregate'
});

export const buildAlertNameVariables = (groupBy?: string[] | null) => {
  const variables = [{ value: '${level}', label: '${level}' }];
  (groupBy || []).filter(Boolean).forEach((field) => {
    const token = '${' + field + '}';
    variables.push({ value: token, label: token });
  });
  return variables;
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

  if (options.isEdit) {
    params.id = options.formData?.id;
  } else {
    params.enable = true;
  }

  return params;
};
