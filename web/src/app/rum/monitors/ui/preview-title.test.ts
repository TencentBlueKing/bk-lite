import { describe, expect, it } from 'vitest';

import { previewOutgoingTitle, type PreviewTitleInput } from '@/app/rum/monitors/ui/preview-title';

const DEFAULT_ERROR_RATE: PreviewTitleInput = {
  application: '',
  severityLabel: '警告',
  metricLabel: '错误率',
  warnLabel: '警告阈值',
  criticalLabel: '严重阈值',
  warn: '3',
  critical: '5',
  comparator: '>=',
  unit: '%',
};

const DEFAULT_PREVIEW = '[警告] — 错误率 警告阈值 3% · 严重阈值 5%（阈 >= 5%）';

describe('previewOutgoingTitle', () => {
  it('locks the default Chinese error-rate sentence with both thresholds', () => {
    const title = previewOutgoingTitle(DEFAULT_ERROR_RATE);
    expect(title).toBe(DEFAULT_PREVIEW);
    for (const part of ['警告', '错误率', '警告阈值', '3', '严重阈值', '5']) {
      expect(title).toContain(part);
    }
    expect(title).not.toContain('warning');
    expect(title).not.toContain('error_rate');
  });

  it('uses the application name and keeps the stored comparator token', () => {
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, application: '  bklite-web  ' })).toBe(
      '[警告] bklite-web 错误率 警告阈值 3% · 严重阈值 5%（阈 >= 5%）',
    );
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, comparator: '>' })).toContain('（阈 > 5%）');
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, comparator: '<=' })).toContain('（阈 <= 5%）');
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, comparator: '<' })).toContain('（阈 < 5%）');
  });

  it('keeps an empty warn visible and appends the input unit', () => {
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, warn: '   ' })).toBe(
      '[警告] — 错误率 警告阈值 — · 严重阈值 5%（阈 >= 5%）',
    );
    expect(previewOutgoingTitle({ ...DEFAULT_ERROR_RATE, warn: '0' })).toContain('警告阈值 0%');
    expect(
      previewOutgoingTitle({
        ...DEFAULT_ERROR_RATE,
        metricLabel: 'LCP P75',
        warn: '200',
        critical: '500',
        unit: 'ms',
      }),
    ).toBe('[警告] — LCP P75 警告阈值 200ms · 严重阈值 500ms（阈 >= 500ms）');
    expect(
      previewOutgoingTitle({
        ...DEFAULT_ERROR_RATE,
        metricLabel: 'CLS P75',
        warn: '0.1',
        critical: '0.25',
        unit: 'Score',
      }),
    ).toBe('[警告] — CLS P75 警告阈值 0.1Score · 严重阈值 0.25Score（阈 >= 0.25Score）');
    expect(
      previewOutgoingTitle({
        ...DEFAULT_ERROR_RATE,
        metricLabel: '会话数',
        warn: '',
        critical: '',
        unit: '',
      }),
    ).toBe('[警告] — 会话数 警告阈值 — · 严重阈值 —（阈 >= —）');
  });
});
