import { describe, expect, it } from 'vitest';

import {
  compareRumIngestStatus,
  matchesRumIngestFilter,
  rumIngestStatus,
  rumIngestStatusTone,
  rumSetupPath,
} from '@/app/rum/lib/ingest';

const now = 1_700_000_000;

describe('rum ingest status', () => {
  it('treats recent accept+store as connected', () => {
    expect(
      rumIngestStatus(
        { enabled: true, lastAcceptedAt: now - 60, lastStoredAt: now - 30 },
        now,
      ),
    ).toBe('connected');
  });

  it('treats accept+store evidence inside the 15-minute window as connected', () => {
    expect(
      rumIngestStatus(
        { enabled: true, lastAcceptedAt: now - 120, lastStoredAt: now - 30 },
        now,
      ),
    ).toBe('connected');
    expect(
      rumIngestStatus(
        { enabled: true, lastAcceptedAt: now - 15 * 60, lastStoredAt: now - 15 * 60 },
        now,
      ),
    ).toBe('connected');
  });

  it('treats stale or missing telemetry as waiting', () => {
    expect(rumIngestStatus({ enabled: true }, now)).toBe('waiting');
    expect(
      rumIngestStatus(
        { enabled: true, lastAcceptedAt: now - 20 * 60, lastStoredAt: now - 30 },
        now,
      ),
    ).toBe('waiting');
    expect(
      rumIngestStatus(
        { enabled: true, lastAcceptedAt: now - 15 * 60 - 1, lastStoredAt: now - 30 },
        now,
      ),
    ).toBe('waiting');
  });

  it('keeps disabled apps out of connected/waiting', () => {
    expect(
      rumIngestStatus(
        { enabled: false, lastAcceptedAt: now - 10, lastStoredAt: now - 10 },
        now,
      ),
    ).toBe('disabled');
    expect(matchesRumIngestFilter('disabled', 'waiting')).toBe(false);
    expect(matchesRumIngestFilter('disabled', 'connected')).toBe(false);
    expect(matchesRumIngestFilter('disabled', 'all')).toBe(true);
  });

  it('sorts waiting before disabled before connected', () => {
    expect(compareRumIngestStatus('waiting', 'connected')).toBeLessThan(0);
    expect(compareRumIngestStatus('disabled', 'connected')).toBeLessThan(0);
  });

  it('maps tones without using primary blue', () => {
    expect(rumIngestStatusTone('connected')).toBe('success');
    expect(rumIngestStatusTone('waiting')).toBe('warning');
    expect(rumIngestStatusTone('disabled')).toBe('neutral');
  });

  it('builds the setup path from the application name', () => {
    expect(rumSetupPath('check out')).toBe('/rum/setup/check%20out');
  });
});
