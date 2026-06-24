/**
 * Parse a receiver input string (comma/newline-separated) into a trimmed string array.
 * Empty entries are filtered out.
 */
export function parseReceiversInput(raw: string): string[] {
  if (!raw || !raw.trim()) return [];
  return raw
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean);
}

export function buildSchedulePayload(
  scheduleEnabled: boolean,
  syncTime: string | undefined
): { enabled: boolean; sync_time: string } {
  return { enabled: scheduleEnabled, sync_time: syncTime ?? '' };
}

export function parseScheduleConfig(
  scheduleConfig: { enabled?: boolean; sync_time?: string } | null | undefined
): { scheduleEnabled: boolean; syncTime: string } {
  if (!scheduleConfig) {
    return { scheduleEnabled: false, syncTime: '' };
  }
  return {
    scheduleEnabled: scheduleConfig.enabled ?? false,
    syncTime: scheduleConfig.sync_time ?? '',
  };
}

export function getDisplayStatusColor(status: string): string {
  const map: Record<string, string> = {
    pending_sync: 'default',
    syncing: 'processing',
    ready: 'success',
    needs_resync: 'warning',
    disabled: 'default',
  };
  return map[status] ?? 'default';
}

export function getSyncRunStatusColor(status: string): string {
  const map: Record<string, string> = {
    running: 'processing',
    success: 'success',
    partial: 'warning',
    failed: 'error',
    never_synced: 'default',
  };
  return map[status] ?? 'default';
}

export function isChannelSendReady(displayStatus: string): boolean {
  return displayStatus === 'ready';
}

export function isChannelSyncRunning(latestSyncStatus: string): boolean {
  return latestSyncStatus === 'running';
}

export function getDisplayStatusText(
  status: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.displayStatus.${status}`);
}

export function getSyncRunStatusText(
  status: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.syncRunStatus.${status || 'never_synced'}`);
}

export function getSyncTriggerModeText(
  triggerMode: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.triggerMode.${triggerMode}`);
}

export function getLatestSyncSummary(
  record: {
    display_sync_status: string;
    latest_sync_matched_count: number | null;
    latest_sync_total_external_user_count: number | null;
    latest_sync_unmatched_count: number | null;
    latest_sync_summary: string;
  },
  t: (key: string, fallback?: string, values?: Record<string, string | number>) => string,
): string {
  const status = record.display_sync_status;
  const matched = record.latest_sync_matched_count ?? 0;
  const total = record.latest_sync_total_external_user_count ?? 0;
  const unmatched = record.latest_sync_unmatched_count ?? 0;

  if (status === 'success') {
    return t(
      'system.channel.imNotificationPage.latestSyncSuccessSummary',
      'Synced {matched_count} users',
      { matched_count: matched },
    );
  }
  if (status === 'partial') {
    return t(
      'system.channel.imNotificationPage.latestSyncPartialSummary',
      'Matched {matched_count}/{total} users, {unmatched} unmatched',
      { matched_count: matched, total, unmatched },
    );
  }
  if (status === 'failed') {
    return record.latest_sync_summary || t('system.channel.imNotificationPage.latestSyncFailedSummary', 'Sync failed');
  }
  if (status === 'running') {
    return t('system.channel.imNotificationPage.latestSyncRunningSummary', 'Syncing');
  }
  return '';
}
