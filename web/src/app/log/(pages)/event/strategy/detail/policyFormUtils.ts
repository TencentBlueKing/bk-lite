import type React from 'react';
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

export const buildLogFieldVariable = (field: string) =>
  field.startsWith('log.') ? '${' + field + '}' : '${log.' + field + '}';

export const buildAlertNameVariables = (groupBy?: string[] | null) => {
  const variableItems = new Map<
    string,
    { value: string; label: string; description: 'alertLevel' | 'groupField' }
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
