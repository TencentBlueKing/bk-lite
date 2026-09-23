export const RUM_INGEST_FRESH_SECONDS = 15 * 60;

export type RumIngestStatus = 'connected' | 'waiting' | 'disabled';
export type RumIngestFilter = 'all' | 'waiting' | 'connected';

const STATUS_ORDER: Record<RumIngestStatus, number> = {
  waiting: 0,
  disabled: 1,
  connected: 2,
};

export function rumIngestStatus(
  app: {
    enabled?: boolean;
    lastAcceptedAt?: number | null;
    lastStoredAt?: number | null;
  },
  nowSec = Date.now() / 1000,
): RumIngestStatus {
  if (!app.enabled) return 'disabled';
  const accepted = app.lastAcceptedAt;
  const stored = app.lastStoredAt;
  if (
    accepted != null &&
    stored != null &&
    nowSec - accepted <= RUM_INGEST_FRESH_SECONDS &&
    nowSec - stored <= RUM_INGEST_FRESH_SECONDS
  ) {
    return 'connected';
  }
  return 'waiting';
}

export function rumIngestStatusTone(status: RumIngestStatus): 'success' | 'warning' | 'neutral' {
  if (status === 'connected') return 'success';
  if (status === 'waiting') return 'warning';
  return 'neutral';
}

export function matchesRumIngestFilter(status: RumIngestStatus, filter: RumIngestFilter): boolean {
  if (filter === 'all') return true;
  return status === filter;
}

export function compareRumIngestStatus(a: RumIngestStatus, b: RumIngestStatus): number {
  return STATUS_ORDER[a] - STATUS_ORDER[b];
}

export function rumSetupPath(name: string): string {
  return `/rum/setup/${encodeURIComponent(name)}`;
}
