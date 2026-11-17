import dayjs from 'dayjs';
import { typeLabel, weekMap } from '@/app/alarm/constants/settings';
import { STATUS_TEXT } from '@/app/alarm/constants/colors';

export interface SuppressionTimeValue {
  type?: string;
  start_time?: string;
  end_time?: string;
  week_month?: ReadonlyArray<number | string>;
}

export type SuppressionLabelTranslate = (key: string, fallback?: string) => string;

const PERIOD_LABEL_KEYS: Record<string, string> = {
  one: 'settings.effectiveOnce',
  day: 'settings.effectiveDaily',
  week: 'settings.effectiveWeekly',
  month: 'settings.effectiveMonthly',
};

const WEEKDAY_LABEL_KEYS = [
  '',
  'settings.weekdayMon',
  'settings.weekdayTue',
  'settings.weekdayWed',
  'settings.weekdayThu',
  'settings.weekdayFri',
  'settings.weekdaySat',
  'settings.weekdaySun',
];

export function localizedSuppressionText(
  translate: SuppressionLabelTranslate | undefined,
  key: string | undefined,
  fallback: string,
): string {
  if (!translate || !key) return fallback;
  const translated = translate(key, fallback);
  if (typeof translated !== 'string' || translated.length === 0 || translated === key) {
    return fallback;
  }
  return translated;
}

export function suppressionPeriodLabel(type: string, translate?: SuppressionLabelTranslate): string {
  return localizedSuppressionText(translate, PERIOD_LABEL_KEYS[type], typeLabel[type] || '');
}

export function suppressionWeekdayLabel(
  day: number,
  translate?: SuppressionLabelTranslate,
  missingFallback = String(day),
): string {
  return localizedSuppressionText(
    translate,
    WEEKDAY_LABEL_KEYS[day],
    weekMap[day] || missingFallback,
  );
}

const RUNTIME_LABEL_KEYS: Record<string, string> = {
  disabled: 'settings.shieldDisplay.runtimeDisabled',
  shielding: 'settings.shieldDisplay.runtimeShielding',
  not_started: 'settings.shieldDisplay.runtimeNotStarted',
  expired: 'settings.shieldDisplay.runtimeExpired',
  outside: 'settings.shieldDisplay.runtimeOutside',
};

function formatClock(time: string, pattern = 'HH:mm:ss'): string {
  const parsed = dayjs(time, pattern);
  return parsed.isValid() ? parsed.format(pattern) : time;
}

function sortedDays(weekMonth: ReadonlyArray<number | string> | undefined): number[] {
  if (!Array.isArray(weekMonth)) return [];
  return weekMonth
    .map((day) => Number(day))
    .filter((day) => Number.isFinite(day))
    .sort((left, right) => left - right);
}

export function formatSuppressionTime(
  value: SuppressionTimeValue | null | undefined,
  translate?: SuppressionLabelTranslate,
): string {
  if (!value || typeof value !== 'object') return '--';
  const type = value.type || '';
  const label = suppressionPeriodLabel(type, translate);
  const start = value.start_time || '';
  const end = value.end_time || '';

  if (type === 'one') {
    if (!start || !end) return label || '--';
    return `${label} ${formatClock(start, 'YYYY-MM-DD HH:mm:ss')}-${formatClock(end, 'YYYY-MM-DD HH:mm:ss')}`.trim();
  }

  let prefix = label;
  const days = sortedDays(value.week_month);
  if (type === 'week') {
    prefix += ` ${days.map((day) => suppressionWeekdayLabel(day, translate)).join(',')}`;
  } else if (type === 'month') {
    prefix += ` ${days.map((day) => `${day}日`).join(',')}`;
  }
  if (!start || !end) return prefix.trim() || '--';
  return `${prefix} ${formatClock(start)} - ${formatClock(end)}`.trim();
}

export function shieldRuntimeLabelKey(status: string | undefined): string {
  if (!status) return '';
  return RUNTIME_LABEL_KEYS[status] || '';
}

export function shieldRuntimeColor(status: string | undefined): string {
  if (status === 'shielding') return STATUS_TEXT.ACTIVE_GREEN;
  if (status === 'disabled') return STATUS_TEXT.INACTIVE_RED;
  if (status === 'expired') return STATUS_TEXT.WARN_ORANGE;
  return STATUS_TEXT.NEUTRAL_GRAY;
}
