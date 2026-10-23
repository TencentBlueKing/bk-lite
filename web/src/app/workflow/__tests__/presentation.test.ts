import { describe, expect, it } from 'vitest';

import {
  formatDuration,
  formatExecutionInfoValue,
  formatStartedBy,
  formatTriggerTypeLabel,
  presentExecutionInfoItem,
} from '../lib/presentation';

const t = (id: string, defaultMessage?: string) => defaultMessage || id;

describe('formatDuration', () => {
  it('matches job-record style for short and long spans', () => {
    expect(formatDuration(null)).toBe('--');
    expect(formatDuration(881)).toBe('881 ms');
    expect(formatDuration(2000)).toBe('2.0 s');
    expect(formatDuration(60_000)).toBe('1m');
    expect(formatDuration(90_000)).toBe('1m 30s');
    expect(formatDuration(3_600_000)).toBe('1h 0m');
    expect(formatDuration(96_521_000)).toBe('26h 48m');
  });
});

describe('formatExecutionInfoValue', () => {
  const convert = (iso: string) => iso.replace('T', ' ').replace(/\.\d+.*$/, '').replace(/\+00:00$/, '').replace(/Z$/, '');

  it('localizes ISO timestamps and keeps other scalars', () => {
    expect(formatExecutionInfoValue('2026-09-22T02:43:06.861846+00:00', convert)).toBe('2026-09-22 02:43:06');
    expect(formatExecutionInfoValue('FAILED', convert)).toBe('FAILED');
    expect(formatExecutionInfoValue(null, convert)).toBe('--');
    expect(formatExecutionInfoValue({ a: 1 }, convert)).toBe('{\n  "a": 1\n}');
  });
});

describe('execution presentation labels', () => {
  const convert = (iso: string) => iso;

  it('maps system starters and trigger types for bilingual display', () => {
    expect(formatStartedBy('workflow-scheduler', t)).toBe('定时调度');
    expect(formatStartedBy('mvp-verifier', t)).toBe('MVP 验收');
    expect(formatStartedBy('admin', t)).toBe('admin');
    expect(formatStartedBy('', t)).toBe('--');
    expect(formatTriggerTypeLabel('FORM', t)).toBe('表单');
    expect(formatTriggerTypeLabel('SCHEDULE', t)).toBe('定时');
  });

  it('maps execution_info labels and enum values', () => {
    expect(presentExecutionInfoItem('status', 'SUCCESS', t, convert)).toEqual({ label: '状态', children: '成功' });
    expect(presentExecutionInfoItem('status', 'FAILED', t, convert)).toEqual({ label: '状态', children: '失败' });
    expect(presentExecutionInfoItem('trigger_type', 'FORM', t, convert)).toEqual({ label: '触发器', children: '表单' });
    expect(presentExecutionInfoItem('started_by', 'workflow-scheduler', t, convert)).toEqual({ label: '发起人', children: '定时调度' });
    expect(presentExecutionInfoItem('duration_ms', 103056, t, convert)).toEqual({ label: '耗时', children: '1m 43s' });
    expect(presentExecutionInfoItem('retry_count', 0, t, convert)).toEqual({ label: '重试次数', children: '0' });
  });
});
