import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  hasFrozenQueryClue,
  hasSnapshotRawData,
  historicalAlertInfo,
  formatClueTimestamp,
  formatPeriod,
  parseAlertCondition,
  parseRawLogData,
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

  it('formats clue timestamps across second, millisecond, and ISO values', () => {
    const mockLocalize = (iso: string) => `localized:${iso}`;
    expect(formatClueTimestamp(1700000000, mockLocalize)).toContain('localized:');
    expect(formatClueTimestamp(1700000000000, mockLocalize)).toContain('localized:');
    expect(formatClueTimestamp('2026-09-16T10:00:00Z', mockLocalize)).toBe('localized:2026-09-16T10:00:00Z');
    expect(formatClueTimestamp(null, mockLocalize)).toBe('--');
    expect(formatClueTimestamp('', mockLocalize)).toBe('--');
  });

  it('formats period values into human-readable strings', () => {
    const t = (_key: string, def?: string) => def || '';
    expect(formatPeriod({ type: 'min', value: 5 }, t)).toBe('5 minute');
    expect(formatPeriod({ type: 'hour', value: 2 }, t)).toBe('2 hour');
    expect(formatPeriod(30, t)).toBe('30s');
    expect(formatPeriod('5m', t)).toBe('5m');
    expect(formatPeriod(null, t)).toBe('--');
    expect(formatPeriod({}, t)).toBe('--');
  });

  it('parses alert condition structures humanely', () => {
    const structured = parseAlertCondition({
      query: 'error AND host:web-1',
      rule: {
        mode: 'and',
        conditions: [
          { field: 'level', op: '=', value: 'error' },
          { field: 'status', op: '>=', value: '500' },
        ],
      },
      group_by: ['host', 'service'],
    });

    expect(structured).toEqual({
      query: 'error AND host:web-1',
      ruleMode: 'AND',
      conditions: [
        { field: 'level', op: '=', value: 'error' },
        { field: 'status', op: '>=', value: '500' },
      ],
      groupBy: ['host', 'service'],
    });

    expect(parseAlertCondition('status >= 500')).toEqual({
      query: 'status >= 500',
    });

    expect(parseAlertCondition({}, 'fallback-query')).toEqual({
      query: 'fallback-query',
    });

    expect(parseAlertCondition(null, null)).toBeNull();
  });

  it('parses raw log data into tabular or fallback json representation', () => {
    // 1. Standard raw log array
    const standardLogs = parseRawLogData([
      { _time: '2026-09-16T10:00:00Z', _msg: 'disk almost full', host: 'web-1' },
      { _time: '2026-09-16T10:00:01Z', _msg: 'disk completely full', host: 'web-1' },
    ]);
    expect(standardLogs.isTabular).toBe(true);
    expect(standardLogs.isAggregate).toBe(false);
    expect(standardLogs.timeKey).toBe('_time');
    expect(standardLogs.messageKey).toBe('_msg');
    expect(standardLogs.rows.length).toBe(2);
    expect(standardLogs.columns.map((c) => c.dataIndex)).toEqual(['_time', '_msg']);

    // 2. Unwrapped single object
    const singleLog = parseRawLogData({
      timestamp: '2026-09-16T10:00:00Z',
      message: 'connection timeout',
    });
    expect(singleLog.isTabular).toBe(true);
    expect(singleLog.timeKey).toBe('timestamp');
    expect(singleLog.messageKey).toBe('message');
    expect(singleLog.rows.length).toBe(1);

    // 3. Aggregate log results
    const aggregateLogs = parseRawLogData([
      { status: 500, count: 42, service: 'auth' },
      { status: 502, count: 18, service: 'gateway' },
    ]);
    expect(aggregateLogs.isTabular).toBe(true);
    expect(aggregateLogs.isAggregate).toBe(true);
    expect(aggregateLogs.columns.map((c) => c.key)).toEqual(['status', 'count', 'service']);
    expect(aggregateLogs.rows.length).toBe(2);

    // 4. Weird shape / non-tabular (plain string or array of strings or nested objects)
    const plainStringLog = parseRawLogData('Fatal crash report');
    expect(plainStringLog.isTabular).toBe(false);

    const stringArrayLog = parseRawLogData(['log line 1', 'log line 2']);
    expect(stringArrayLog.isTabular).toBe(false);

    const nestedComplexLog = parseRawLogData([{ nested: { deeply: true } }]);
    expect(nestedComplexLog.isTabular).toBe(false);
  });
});
