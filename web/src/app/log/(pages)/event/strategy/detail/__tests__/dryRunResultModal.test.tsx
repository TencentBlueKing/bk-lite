import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import DryRunResultModal, { LogDryRunResult } from '../dryRunResultModal';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
});

const t = (key: string) => key;

const renderModal = (data: LogDryRunResult) =>
  render(<DryRunResultModal open data={data} onClose={vi.fn()} t={t} />);

describe('试算结果弹窗', () => {
  it('展示判定标签、截断提示和样本', () => {
    renderModal({
      alert_type: 'aggregate',
      baseline_status: 'ok',
      truncated: true,
      window: { start: 1761550000, end: 1761550300 },
      previous_window: { start: 1761549700, end: 1761550000 },
      items: [
        {
          group: { service: 'order' },
          count: 180,
          previous_count: 50,
          count_rate: 0.6,
          count_delta: 130,
          verdict: 'would_trigger',
        },
        {
          group: {},
          count: null,
          verdict: 'missing_baseline',
        },
      ],
      sample_preview: [{ _time: '2026-10-27T07:55:00Z', _msg: 'order exploded' }],
    });

    expect(screen.getByTestId('dry-run-previous-window').textContent).toContain(
      'log.event.dryRunPreviousWindow',
    );
    expect(screen.getByText('log.event.truncatedHint')).toBeTruthy();
    expect(screen.getByText('service=order')).toBeTruthy();
    expect(screen.getByText('common.all')).toBeTruthy();
    expect(screen.getByText('0.60')).toBeTruthy();
    const trigger = screen.getByTestId('dry-run-verdict-would-trigger');
    expect(trigger.getAttribute('style') || '').toContain('--color-fail');
    expect(screen.getAllByText('log.event.verdictMissingBaseline').length).toBeGreaterThan(0);
    expect(screen.getByText('order exploded')).toBeTruthy();
  });

  it('没有分组行时显示本窗无匹配日志', () => {
    renderModal({
      alert_type: 'aggregate',
      baseline_status: 'not_required',
      items: [],
    });

    expect(screen.getByText('log.event.dryRunNoMatch')).toBeTruthy();
    expect(screen.queryByTestId('dry-run-previous-window')).toBeNull();
    expect(screen.queryByText('log.event.previousCount')).toBeNull();
  });

  it('关键字模式只显示分组和本窗条数', () => {
    renderModal({
      alert_type: 'keyword',
      baseline_status: 'not_required',
      items: [{ group: { service: 'pay' }, count: 4, verdict: 'would_trigger' }],
    });

    expect(screen.getByText('log.event.currentCount')).toBeTruthy();
    expect(screen.queryByText('log.event.previousCount')).toBeNull();
    expect(screen.queryByText('log.event.countRate')).toBeNull();
    expect(screen.queryByText('log.event.countDelta')).toBeNull();
    expect(screen.getByText('service=pay')).toBeTruthy();
    expect(screen.getByTestId('dry-run-verdict-would-trigger')).toBeTruthy();
  });

  it('展开行显示条件子表和原因，多个对照分别显示', () => {
    renderModal({
      alert_type: 'aggregate',
      baseline_status: 'ok',
      window: { start: 1761550000, end: 1761550300 },
      previous_window: { start: 1761549700, end: 1761550000 },
      baselines: {
        offset_24h: { window: { start: 1761463700, end: 1761464000 }, status: 'ok' },
        previous_window: { window: { start: 1761549700, end: 1761550000 }, status: 'unavailable' },
      },
      items: [
        {
          group: { service: 'cart' },
          count: 15,
          verdict: 'no_trigger',
          reason: 'baseline_zero',
          conditions: [
            {
              func: 'count',
              field: '_msg',
              current: 15,
              baseline: 0,
              value: null,
              op: '>',
              threshold: '50',
              matched: false,
              reason: 'baseline_zero',
              compare: { kind: 'percent', to: 'offset_24h' },
            },
          ],
        },
      ],
    });

    expect(screen.getByTestId('dry-run-baseline-offset_24h').textContent).toContain('ok');
    expect(screen.getByTestId('dry-run-baseline-previous_window').textContent).toContain('unavailable');
    fireEvent.click(screen.getByRole('button', { name: /expand row/i }));
    expect(screen.getByText('count percent')).toBeTruthy();
    expect(screen.getByText('log.event.reasonBaselineZero')).toBeTruthy();
    expect(screen.getByText('log.event.baselineValue')).toBeTruthy();
    expect(screen.getByText('log.event.computedValue')).toBeTruthy();
  });

  it('无数据胶囊和本窗无日志行', () => {
    renderModal({
      alert_type: 'aggregate',
      baseline_status: 'not_required',
      items: [
        {
          group: { host: 'b' },
          count: 0,
          no_data: true,
          verdict: 'would_trigger_no_data',
        },
      ],
    });

    expect(screen.getByText('log.event.verdictWouldTriggerNoData 1')).toBeTruthy();
    expect(screen.getByText('log.event.currentWindowEmpty')).toBeTruthy();
    expect(screen.getByText('host=b')).toBeTruthy();
  });
});
