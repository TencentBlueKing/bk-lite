import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  hasFrozenQueryClue,
  hasSnapshotRawData,
  historicalAlertInfo,
} from '../alertRawLogEvidence';

const widgetSource = readFileSync(
  resolve(
    dirname(fileURLToPath(import.meta.url)),
    '../AlertRawLogWidget.tsx',
  ),
  'utf8',
);

describe('AlertRawLogWidget history contract', () => {
  it('loads saved snapshots and never regenerates from the live policy', () => {
    const apiSource = readFileSync(
      resolve(
        dirname(fileURLToPath(import.meta.url)),
        '../../../api/event.ts',
      ),
      'utf8',
    );
    expect(widgetSource).toContain('getAlertSnapshots');
    expect(apiSource).toContain('/log/alert/snapshots/');
    expect(widgetSource).toContain('query_clue');
    expect(widgetSource).toContain('queryClue');
    expect(widgetSource).toContain('originalLog');
    expect(widgetSource).not.toContain('getEventRaw');
    expect(widgetSource).not.toContain('last_event');
    expect(widgetSource).not.toContain('previewMonitorPolicy');
    expect(widgetSource).not.toContain('previewPolicy');
    expect(widgetSource).not.toContain('policy_scan');
    expect(widgetSource).not.toContain('/log/policy');
    expect(widgetSource).not.toContain('VictoriaLogs');
    expect(widgetSource).not.toContain('getPolicy');
  });
});

describe('alert raw log evidence', () => {
  it('distinguishes missing query clue from missing raw data', () => {
    expect(hasFrozenQueryClue(undefined)).toBe(false);
    expect(hasFrozenQueryClue({})).toBe(false);
    expect(hasFrozenQueryClue({ query: 'error' })).toBe(true);
    expect(hasSnapshotRawData(undefined)).toBe(false);
    expect(hasSnapshotRawData([])).toBe(false);
    expect(hasSnapshotRawData([{"_msg": "hit"}])).toBe(true);
    expect(
      historicalAlertInfo({
        id: 'a1',
        source_id: 'policy_1',
        level: 'warning',
        content: 'hit',
        start_event_time: '2026-09-15T08:00:00Z',
        status: 'closed',
      } as { id: string; source_id: string; level: string; content: string; start_event_time: string; status: string }),
    ).toEqual({
      id: 'a1',
      source_id: 'policy_1',
      level: 'warning',
      content: 'hit',
      start_event_time: '2026-09-15T08:00:00Z',
    });
  });
});
