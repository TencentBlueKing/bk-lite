import type { PhaseProgressEntry, RunStatus, UserSyncRun, UserSyncSource } from '@/app/system-manager/types/user-sync';
import {
  formatSyncGroupsChangeParts,
  formatSyncUsersChangeParts,
  formatUserSyncErrorMessage,
} from '@/app/system-manager/utils/userSyncProgress';

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

export function validateRequiredUserMapping(rows: MappingRow[]): boolean {
  return rows.some(
    (row) => row.platformField === 'username' && row.externalField.trim().length > 0,
  );
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

function formatTemplate(
  template: string,
  replacements: Record<string, string | number>
): string {
  return Object.entries(replacements).reduce(
    (text, [key, value]) => text.replaceAll(`{{${key}}}`, String(value)),
    template
  );
}

interface EmailStatus {
  total?: number;
  sent?: number;
  failed?: number;
  completed?: boolean;
}

function getEmailStatusSummary(
  emailStatus: EmailStatus | undefined,
  t: (key: string, fallback?: string) => string
): string {
  if (!emailStatus) return '';

  const total = Number(emailStatus.total || 0);
  const sent = Number(emailStatus.sent || 0);
  const failed = Number(emailStatus.failed || 0);

  if (!emailStatus.completed) {
    return formatTemplate(t('system.user.userSyncPage.runSummary.emailSending'), { total });
  }
  if (failed === 0) {
    return formatTemplate(t('system.user.userSyncPage.runSummary.emailSent'), { sent });
  }
  if (sent > 0) {
    return formatTemplate(t('system.user.userSyncPage.runSummary.emailPartialFailed'), { sent, failed });
  }
  return formatTemplate(t('system.user.userSyncPage.runSummary.emailFailed'), { failed });
}

export function getUserSyncRunSummary(
  record: Pick<RecordRow, 'status' | 'summary' | 'synced_user_count' | 'synced_group_count' | 'payload'>,
  t: (key: string, fallback?: string) => string
): string {
  const payload = (record.payload || {}) as {
    errors?: Array<{ message?: string }>;
    conflict_usernames?: string[];
    conflict_user_count?: number;
    input_summary?: {
      fetched_user_count?: number;
      fetched_group_count?: number;
    };
    email_status?: EmailStatus;
    phase_progress?: {
      sync_users?: { total?: number; counters?: PhaseProgressEntry['counters'] };
      sync_groups?: { total?: number; counters?: PhaseProgressEntry['counters'] };
    };
  };
  const conflictUsernames = Array.isArray(payload.conflict_usernames) ? payload.conflict_usernames : [];
  const conflictCount = Number(payload.conflict_user_count ?? conflictUsernames.length ?? 0);
  const firstErrorMessage = payload.errors?.[0]?.message || '';
  const externalSummary = formatTemplate(t('system.user.userSyncPage.runSummary.externalCounts'), {
    users: payload.input_summary?.fetched_user_count ?? '--',
    groups: payload.input_summary?.fetched_group_count ?? '--',
  });
  const userEntry = payload.phase_progress?.sync_users;
  const groupEntry = payload.phase_progress?.sync_groups;
  const hasPhaseLedger = Boolean(userEntry?.counters || groupEntry?.counters);
  const usersLedger = hasPhaseLedger
    ? formatTemplate(t('system.user.userSyncPage.runSummary.userLedger'), {
      parts: formatSyncUsersChangeParts(
        userEntry?.counters,
        Number(userEntry?.total ?? payload.input_summary?.fetched_user_count ?? record.synced_user_count ?? 0),
        t,
        'summary',
      ).join(' · ') || String(record.synced_user_count),
    })
    : '';
  const groupsLedger = hasPhaseLedger
    ? formatTemplate(t('system.user.userSyncPage.runSummary.groupLedger'), {
      parts: formatSyncGroupsChangeParts(
        groupEntry?.counters,
        Number(groupEntry?.total ?? payload.input_summary?.fetched_group_count ?? record.synced_group_count ?? 0),
        t,
        'summary',
      ).join(' · ') || String(record.synced_group_count),
    })
    : '';

  let summary: string;
  if (record.status === 'success') {
    if (hasPhaseLedger) {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.successWithLedger'), {
        external: externalSummary,
        users: usersLedger,
        groups: groupsLedger,
      });
    } else {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.success'), {
        external: externalSummary,
        users: record.synced_user_count,
        groups: record.synced_group_count,
      });
    }
  } else if (record.status === 'partial') {
    if (hasPhaseLedger) {
      summary = formatTemplate(
        t(
          conflictUsernames.length > 0
            ? 'system.user.userSyncPage.runSummary.partialWithLedgerAndUsers'
            : 'system.user.userSyncPage.runSummary.partialWithLedger',
        ),
        {
          external: externalSummary,
          users: usersLedger,
          groups: groupsLedger,
          usernames: conflictUsernames.join(t('system.user.userSyncPage.runSummary.usernameListSeparator')),
        },
      );
    } else if (conflictUsernames.length > 0) {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.partialWithUsers'), {
        external: externalSummary,
        users: record.synced_user_count,
        groups: record.synced_group_count,
        conflicts: conflictCount,
        usernames: conflictUsernames.join(t('system.user.userSyncPage.runSummary.usernameListSeparator')),
      });
    } else {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.partial'), {
        external: externalSummary,
        users: record.synced_user_count,
        groups: record.synced_group_count,
        conflicts: conflictCount,
      });
    }
  } else if (record.status === 'failed') {
    if (hasPhaseLedger) {
      summary = formatTemplate(
        t(
          conflictUsernames.length > 0
            ? 'system.user.userSyncPage.runSummary.failedWithLedgerAndUsers'
            : 'system.user.userSyncPage.runSummary.failedWithLedger',
        ),
        {
          external: externalSummary,
          users: usersLedger,
          groups: groupsLedger,
          usernames: conflictUsernames.join(t('system.user.userSyncPage.runSummary.usernameListSeparator')),
        },
      );
      if (firstErrorMessage) {
        summary = formatTemplate(t('system.user.userSyncPage.runSummary.withReason'), {
          summary,
          reason: firstErrorMessage,
        });
      }
    } else if (firstErrorMessage) {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.failed'), {
        external: externalSummary,
        reason: firstErrorMessage,
      });
    } else if (conflictUsernames.length > 0) {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.failedConflict'), {
        external: externalSummary,
        users: record.synced_user_count,
        groups: record.synced_group_count,
        conflicts: conflictCount,
        usernames: conflictUsernames.join(t('system.user.userSyncPage.runSummary.usernameListSeparator')),
      });
    } else {
      summary = formatTemplate(t('system.user.userSyncPage.runSummary.result'), {
        external: externalSummary,
        summary: formatUserSyncErrorMessage(record.summary, t),
      });
    }
  } else {
    summary = formatTemplate(t('system.user.userSyncPage.runSummary.result'), {
      external: externalSummary,
      summary: record.summary,
    });
  }

  const emailSummary = getEmailStatusSummary(payload.email_status, t);
  return emailSummary
    ? formatTemplate(t('system.user.userSyncPage.runSummary.withEmailStatus'), {
      summary,
      email: emailSummary,
    })
    : summary;
}
