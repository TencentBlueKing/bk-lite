import { SCHEDULE_UNIT_MAP } from '@/app/monitor/constants/event';

export const DURATION_UNIT_OPTIONS = [
  { value: 'min', label: '分钟' },
  { value: 'hour', label: '小时' },
  { value: 'day', label: '天' },
] as const;

export const NO_DATA_LEVEL_OPTIONS = [
  { value: 'critical', label: '严重' },
  { value: 'error', label: '错误' },
  { value: 'warning', label: '警告' },
] as const;

export type DurationUnit = (typeof DURATION_UNIT_OPTIONS)[number]['value'];
export type NoDataLevel = (typeof NO_DATA_LEVEL_OPTIONS)[number]['value'];

const ALERT_NAME_MAX = 200;
const UNIT_SECONDS: Record<DurationUnit, number> = {
  min: 60,
  hour: 3600,
  day: 86400,
};

export interface DurationValue {
  type?: string;
  value?: number | null;
}

export interface PolicyGroupNoDataInput {
  enabled?: boolean;
  period?: DurationValue;
  level?: string;
  alert_name?: string;
  recovery_period?: DurationValue;
}

export interface DetectionDraft {
  scheduleValue: number | null;
  scheduleUnit: DurationUnit;
  noDataEnabled: boolean | null;
  noDataAlertName: string;
  noDataPeriodValue: number;
  noDataPeriodUnit: DurationUnit;
  noDataLevel: NoDataLevel;
  noDataRecoveryValue: number;
  noDataRecoveryUnit: DurationUnit;
}

export interface DetectionSaveScope {
  scheduleUniform?: boolean;
  noDataUniform?: boolean;
  initial?: DetectionDraft;
}

export interface PolicyGroupDetectionBadgeInput {
  scheduleUniform?: boolean;
  noDataUniform?: boolean;
}

export interface RecoveryThresholdDraft {
  method?: string;
  value?: number | null;
}

export interface RuleEditDraft {
  queryType: string;
  threshold: unknown;
  conditionThresholds: Record<string, unknown>;
  alertName: string;
  triggerCount: number | null;
  recoveryCondition: number | null;
  recoveryThreshold: RecoveryThresholdDraft;
}

const isDurationUnit = (value: string | undefined): value is DurationUnit =>
  value === 'min' || value === 'hour' || value === 'day';

const isNoDataLevel = (value: string | undefined): value is NoDataLevel =>
  value === 'critical' || value === 'error' || value === 'warning';

export const durationBounds = (unit: string) => {
  const normalized: DurationUnit = isDurationUnit(unit) ? unit : 'min';
  return {
    min: SCHEDULE_UNIT_MAP[`${normalized}Min`],
    max: SCHEDULE_UNIT_MAP[`${normalized}Max`],
  };
};

const storedDuration = (
  value: DurationValue | undefined,
  fallback: { unit: DurationUnit; value: number }
) => {
  const unit = isDurationUnit(value?.type) ? value.type : fallback.unit;
  const number = value?.value;
  if (typeof number !== 'number' || !Number.isInteger(number) || number < 1) {
    return { unit: fallback.unit, value: fallback.value };
  }
  return { unit, value: number };
};

const positiveDuration = (
  value: DurationValue | undefined,
  fallback: { unit: DurationUnit; value: number }
) => {
  const unit = isDurationUnit(value?.type) ? value.type : fallback.unit;
  const number = value?.value;
  const bounds = durationBounds(unit);
  if (typeof number !== 'number' || !Number.isInteger(number) || number < bounds.min || number > bounds.max) {
    return { unit: fallback.unit, value: fallback.value };
  }
  return { unit, value: number };
};

export const detectionDraftFromGroup = (
  group: {
    schedule?: DurationValue | null;
    no_data?: PolicyGroupNoDataInput | null;
  },
  scope: Pick<DetectionSaveScope, 'scheduleUniform' | 'noDataUniform'> = {}
): DetectionDraft => {
  const schedule = positiveDuration(group.schedule || undefined, { unit: 'min', value: 5 });
  const noData = group.no_data || {};
  const period = storedDuration(noData.period, { unit: 'min', value: 10 });
  const recovery = storedDuration(noData.recovery_period, { unit: 'min', value: 10 });
  return {
    scheduleValue: scope.scheduleUniform === false ? null : schedule.value,
    scheduleUnit: scope.scheduleUniform === false ? 'min' : schedule.unit,
    noDataEnabled: scope.noDataUniform === false ? null : Boolean(noData.enabled),
    noDataAlertName: scope.noDataUniform === false ? '' : (typeof noData.alert_name === 'string' ? noData.alert_name : ''),
    noDataPeriodValue: period.value,
    noDataPeriodUnit: period.unit,
    noDataLevel: isNoDataLevel(noData.level) ? noData.level : 'warning',
    noDataRecoveryValue: recovery.value,
    noDataRecoveryUnit: recovery.unit,
  };
};

const integerInBounds = (value: number | null, unit: string) => {
  if (value == null || !Number.isInteger(value)) return false;
  const bounds = durationBounds(unit);
  return value >= bounds.min && value <= bounds.max;
};

const scheduleChanged = (draft: DetectionDraft, initial: DetectionDraft | undefined) => {
  if (!initial) return draft.scheduleValue != null;
  return draft.scheduleValue !== initial.scheduleValue || draft.scheduleUnit !== initial.scheduleUnit;
};

const noDataChanged = (draft: DetectionDraft, initial: DetectionDraft | undefined) => {
  if (!initial) return draft.noDataEnabled != null;
  return draft.noDataEnabled !== initial.noDataEnabled
    || draft.noDataAlertName !== initial.noDataAlertName
    || draft.noDataPeriodValue !== initial.noDataPeriodValue
    || draft.noDataPeriodUnit !== initial.noDataPeriodUnit
    || draft.noDataLevel !== initial.noDataLevel
    || draft.noDataRecoveryValue !== initial.noDataRecoveryValue
    || draft.noDataRecoveryUnit !== initial.noDataRecoveryUnit;
};

export const detectionSections = (draft: DetectionDraft, scope: DetectionSaveScope = {}) => ({
  schedule: scope.scheduleUniform !== false || scheduleChanged(draft, scope.initial),
  noData: scope.noDataUniform !== false || noDataChanged(draft, scope.initial),
});

export const detectionSaveBlocker = (draft: DetectionDraft, scope: DetectionSaveScope = {}): string | null => {
  const sections = detectionSections(draft, scope);
  if (!sections.schedule && !sections.noData) return '没有需要保存的变更';
  if (sections.schedule && !integerInBounds(draft.scheduleValue, draft.scheduleUnit)) return '请填写有效的检测频率';
  if (!sections.noData || !draft.noDataEnabled) return null;
  const name = draft.noDataAlertName.trim();
  if (!name) return '请填写无数据告警名称';
  if (draft.noDataAlertName.length > ALERT_NAME_MAX) return '无数据告警名称过长';
  if (!positiveCount(draft.noDataPeriodValue)) return '请填写有效的无数据检测窗';
  if (!positiveCount(draft.noDataRecoveryValue)) return '请填写有效的无数据恢复窗';
  const periodSeconds = draft.noDataPeriodValue * UNIT_SECONDS[draft.noDataPeriodUnit];
  const recoverySeconds = draft.noDataRecoveryValue * UNIT_SECONDS[draft.noDataRecoveryUnit];
  if (periodSeconds < recoverySeconds) return '无数据检测窗不能小于恢复窗';
  return null;
};

export interface PolicyGroupDetectionPayload {
  group_id: number;
  schedule?: { type: DurationUnit; value: number };
  no_data?:
    | { enabled: false }
    | {
        enabled: true;
        period: { type: DurationUnit; value: number };
        level: NoDataLevel;
        alert_name: string;
        recovery_period: { type: DurationUnit; value: number };
      };
}

export const buildPolicyGroupDetectionPayload = (
  groupId: number,
  draft: DetectionDraft,
  scope: DetectionSaveScope = {}
): PolicyGroupDetectionPayload => {
  const sections = detectionSections(draft, scope);
  const payload: PolicyGroupDetectionPayload = { group_id: groupId };
  if (sections.schedule && draft.scheduleValue != null) {
    payload.schedule = { type: draft.scheduleUnit, value: draft.scheduleValue };
  }
  if (!sections.noData || draft.noDataEnabled == null) return payload;
  if (!draft.noDataEnabled) {
    payload.no_data = { enabled: false };
    return payload;
  }
  payload.no_data = {
    enabled: true,
    period: { type: draft.noDataPeriodUnit, value: draft.noDataPeriodValue },
    level: draft.noDataLevel,
    alert_name: draft.noDataAlertName,
    recovery_period: { type: draft.noDataRecoveryUnit, value: draft.noDataRecoveryValue },
  };
  return payload;
};

const noDataDocumentChanged = (
  noData: Extract<PolicyGroupDetectionPayload['no_data'], { enabled: true }>,
  initial: DetectionDraft | undefined
) => {
  if (!initial) return false;
  return initial.noDataPeriodValue !== noData.period.value
    || initial.noDataPeriodUnit !== noData.period.type
    || initial.noDataRecoveryValue !== noData.recovery_period.value
    || initial.noDataRecoveryUnit !== noData.recovery_period.type
    || initial.noDataLevel !== noData.level
    || initial.noDataAlertName !== noData.alert_name;
};

export const detectionConfirm = (payload: PolicyGroupDetectionPayload, initial?: DetectionDraft) => {
  const lines: string[] = [];
  const scheduleDiffers = Boolean(payload.schedule) && (
    !initial
    || initial.scheduleValue !== payload.schedule?.value
    || initial.scheduleUnit !== payload.schedule?.type
  );
  if (scheduleDiffers) lines.push('保存后这一组按这个频率扫描。');
  const turningNoDataOff = payload.no_data?.enabled === false && initial?.noDataEnabled !== false;
  if (turningNoDataOff) lines.push('保存后结束未恢复的无数据告警。');
  else if (payload.no_data?.enabled === true && initial?.noDataEnabled !== true) {
    lines.push('保存后无数据告警按插件写到承载规则上。');
  } else if (payload.no_data?.enabled === true && noDataDocumentChanged(payload.no_data, initial)) {
    lines.push('保存后按新的无数据条件检测，正在响的无数据告警不结束。');
  }
  return {
    title: turningNoDataOff && !scheduleDiffers ? '关闭无数据告警' : '修改检测配置',
    content: lines.join(''),
  };
};

export const policyGroupDetectionBadges = ({
  scheduleUniform = true,
  noDataUniform = true,
}: PolicyGroupDetectionBadgeInput): string[] => {
  const badges: string[] = [];
  if (scheduleUniform === false) badges.push('频率不一致');
  if (noDataUniform === false) badges.push('无数据不一致');
  return badges;
};

export type PolicyGroupConfigTab = 'detection' | 'notice';

/** 配置抽屉先停在有缺口的那一页。检测保存会结束告警，两页都有缺口时先看检测。 */
export const defaultConfigTab = (detectionBadges: string[], noticeBadges: string[]): PolicyGroupConfigTab =>
  detectionBadges.length === 0 && noticeBadges.length > 0 ? 'notice' : 'detection';

export const policyGroupDetectionNotes = ({
  scheduleUniform = true,
  noDataUniform = true,
}: PolicyGroupDetectionBadgeInput): string[] => {
  const notes: string[] = [];
  if (scheduleUniform === false) notes.push('组内检测频率不一致，保存后会写成同一套。');
  if (noDataUniform === false) notes.push('组内无数据告警不一致，保存后会写成同一套。');
  return notes;
};

const stable = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map((item) => stable(item)).join(',')}]`;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${key}:${stable(record[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value ?? null);
};

const normalizedRecovery = (value: RecoveryThresholdDraft | undefined) => {
  if (value?.value == null || !Number.isFinite(value.value)) return null;
  return { method: value.method || '>', value: value.value };
};

export const ruleEditDraftFromRule = (rule: {
  query_type?: string;
  threshold?: unknown;
  condition_thresholds?: Record<string, unknown>;
  alert_name?: string;
  trigger_count?: number;
  recovery_condition?: number;
  recovery_threshold?: RecoveryThresholdDraft;
}): RuleEditDraft => ({
  queryType: rule.query_type || '',
  threshold: rule.threshold || [],
  conditionThresholds: rule.condition_thresholds || {},
  alertName: rule.alert_name || '',
  triggerCount: rule.trigger_count ?? 1,
  recoveryCondition: rule.recovery_condition ?? 1,
  recoveryThreshold: {
    method: rule.recovery_threshold?.method || '>',
    value: rule.recovery_threshold?.value ?? null,
  },
});

export const ruleEditClosesAlerts = (original: RuleEditDraft, draft: RuleEditDraft) => {
  if (draft.queryType === 'multi') {
    if (stable(original.conditionThresholds) !== stable(draft.conditionThresholds)) return true;
  } else if (stable(original.threshold) !== stable(draft.threshold)) {
    return true;
  }
  if (original.triggerCount !== draft.triggerCount) return true;
  if (original.recoveryCondition !== draft.recoveryCondition) return true;
  const recoveryChanged = draft.queryType !== 'multi'
    && stable(normalizedRecovery(original.recoveryThreshold)) !== stable(normalizedRecovery(draft.recoveryThreshold));
  if (recoveryChanged) return true;
  return false;
};

export const ruleEditConfirm = ({
  closesAlerts,
  alertNameChanged,
  openAlertCount,
}: {
  closesAlerts: boolean;
  alertNameChanged: boolean;
  openAlertCount: number;
}) => {
  if (closesAlerts) {
    return {
      title: '修改规则',
      content: `保存后按新的检测条件检测，并结束这条规则上 ${openAlertCount} 条未恢复告警。`,
    };
  }
  if (alertNameChanged) {
    return {
      title: '修改告警名称',
      content: '保存后新告警使用新名称。正在响的告警不结束。',
    };
  }
  return {
    title: '修改规则',
    content: '保存后不会结束正在响的告警。',
  };
};

const positiveCount = (value: number | null) =>
  typeof value === 'number' && Number.isInteger(value) && value >= 1;

export const ruleSaveBlocker = (draft: RuleEditDraft): string | null => {
  if (!draft.alertName.trim()) return '请填写告警名称';
  if (draft.alertName.length > ALERT_NAME_MAX) return '告警名称过长';
  if (!positiveCount(draft.triggerCount)) return '连续触发周期必须是大于等于 1 的整数';
  if (!positiveCount(draft.recoveryCondition)) return '连续恢复周期必须是大于等于 1 的整数';
  return null;
};

export const buildPolicyGroupRulePayload = (groupId: number, ruleId: number, draft: RuleEditDraft) => {
  const payload: {
    group_id: number;
    rule_id: number;
    alert_name: string;
    trigger_count: number;
    recovery_condition: number;
    threshold?: unknown;
    condition_thresholds?: Record<string, unknown>;
    recovery_threshold?: { method: string; value: number } | Record<string, never>;
  } = {
    group_id: groupId,
    rule_id: ruleId,
    alert_name: draft.alertName,
    trigger_count: draft.triggerCount as number,
    recovery_condition: draft.recoveryCondition as number,
  };
  if (draft.queryType === 'multi') {
    payload.condition_thresholds = draft.conditionThresholds;
    return payload;
  }
  payload.threshold = draft.threshold;
  const recovery = normalizedRecovery(draft.recoveryThreshold);
  payload.recovery_threshold = recovery ? { method: recovery.method, value: recovery.value } : {};
  return payload;
};
