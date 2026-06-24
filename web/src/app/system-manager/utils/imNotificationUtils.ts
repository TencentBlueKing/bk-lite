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
  return t(`system.channel.imNotificationPage.syncRunStatus.${status}`);
}

export function getSyncTriggerModeText(
  triggerMode: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.triggerMode.${triggerMode}`);
}
