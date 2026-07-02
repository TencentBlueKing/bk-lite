import type { RunStatus, UserSyncRun, UserSyncSource } from '@/app/system-manager/types/user-sync';

export const RUN_STATUS_TEXT_STYLE: Record<RunStatus, string> = {
  running: 'processing',
  success: 'success',
  failed: 'error',
  partial: 'default',
};

export interface ProviderMeta {
  short: string;
  bg: string;
  text: string;
  label: string;
}

export interface MappingRow {
  platformField: string;
  externalField: string;
}

export interface RecordRow extends UserSyncRun {
  source_name: string;
}

export const FIXED_PLATFORM_FIELD_ORDER = ['username', 'display_name', 'email', 'phone'] as const;

export const PLATFORM_FIELD_META: Record<(typeof FIXED_PLATFORM_FIELD_ORDER)[number], { label: string; desc: string }> = {
  username: { label: '用户名', desc: '系统登录唯一标识' },
  display_name: { label: '显示名', desc: '用户展示名称' },
  email: { label: '邮箱', desc: '用户邮箱地址' },
  phone: { label: '手机号', desc: '用户联系电话' },
};

export function toMappingRows(fieldMapping: Record<string, unknown> | undefined): MappingRow[] {
  const mapping = fieldMapping || {};
  return FIXED_PLATFORM_FIELD_ORDER.map((key) => ({
    platformField: key,
    externalField: String(mapping[key] || ''),
  }));
}

export function toFieldMappingPayload(rows: MappingRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((acc, item) => {
    const key = item.platformField.trim();
    const value = item.externalField.trim();
    if (key && value) {
      acc[key] = value;
    }
    return acc;
  }, {});
}

export function updateMappingRowField(
  rows: MappingRow[],
  index: number,
  externalField: string,
): MappingRow[] {
  return rows.map((row, rowIndex) => {
    if (rowIndex !== index) {
      return row;
    }
    return { ...row, externalField };
  });
}

export function getScheduleSummary(
  scheduleConfig: UserSyncSource['schedule_config'],
  enabled: boolean,
  t: (key: string, fallback?: string) => string
): string {
  if (!enabled) return t('system.user.userSyncPage.scheduleSummaryStopped');
  if (!scheduleConfig || scheduleConfig.mode === 'disabled') {
    return t('system.user.userSyncPage.manualSync');
  }
  if (scheduleConfig.mode === 'daily') {
    return t('system.user.userSyncPage.scheduleSummaryDaily').replace('{{time}}', String(scheduleConfig.time || '--'));
  }
  if (scheduleConfig.mode === 'weekly') {
    const weekdayLabels = (scheduleConfig.weekdays || [])
      .map((day) => t(`system.user.userSyncPage.weekdays.${day}`))
      .join('、');
    return t('system.user.userSyncPage.scheduleSummaryWeekly')
      .replace('{{weekdays}}', weekdayLabels)
      .replace('{{time}}', String(scheduleConfig.time || '--'));
  }
  return t('system.user.userSyncPage.scheduleSummaryInterval')
    .replace('{{hours}}', String(scheduleConfig.interval_hours || '--'));
}
