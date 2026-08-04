import axios, { AxiosError } from 'axios';
import { describe, expect, it } from 'vitest';

import { buildDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import { classifyWidgetQueryError } from '@/app/ops-analysis/utils/requestError';

/**
 * Production path (A1):
 * Widget query failure → classifyWidgetQueryError → onRenderStatus.errorCode
 * → buildDashboardRenderSignal → report-failed.errorCode
 * → backend resolve_report_failed_semantics → data_load / RetryClassifier
 */
describe('Widget query errorCode production path', () => {
  it('timeout axios error → report-failed carries widget_query_timeout', () => {
    const err = new AxiosError(
      'timeout of 30000ms exceeded',
      'ECONNABORTED',
    );
    const errorCode = classifyWidgetQueryError(err);
    expect(errorCode).toBe('widget_query_timeout');

    const results = new Map([
      [
        'chart-1',
        {
          widgetId: 'chart-1',
          status: 'failed' as const,
          error: err.message,
          errorCode,
        },
      ],
    ]);
    const signal = buildDashboardRenderSignal(8, ['chart-1'], results);

    expect(signal).toEqual({
      type: 'report-failed',
      dashboardId: '8',
      widgets: [
        {
          widgetId: 'chart-1',
          status: 'failed',
          error: 'timeout of 30000ms exceeded',
          errorCode: 'widget_query_timeout',
        },
      ],
      widgetId: 'chart-1',
      error: 'timeout of 30000ms exceeded',
      errorCode: 'widget_query_timeout',
    });
  });

  it('network transient → widget_query_transient on signal', () => {
    const err = new AxiosError('Network Error', 'ERR_NETWORK');
    expect(classifyWidgetQueryError(err)).toBe('widget_query_transient');

    const signal = buildDashboardRenderSignal(
      8,
      ['w1'],
      new Map([
        [
          'w1',
          {
            widgetId: 'w1',
            status: 'failed',
            error: 'Network Error',
            errorCode: classifyWidgetQueryError(err),
          },
        ],
      ]),
    );
    expect(signal?.errorCode).toBe('widget_query_transient');
  });

  it('403 → widget_data_forbidden on signal', () => {
    const err = new AxiosError(
      'Request failed with status code 403',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 403,
        statusText: 'Forbidden',
        headers: {},
        config: {} as never,
        data: {},
      },
    );
    expect(classifyWidgetQueryError(err)).toBe('widget_data_forbidden');

    const signal = buildDashboardRenderSignal(
      8,
      ['w1'],
      new Map([
        [
          'w1',
          {
            widgetId: 'w1',
            status: 'failed',
            error: 'forbidden',
            errorCode: classifyWidgetQueryError(err),
          },
        ],
      ]),
    );
    expect(signal?.errorCode).toBe('widget_data_forbidden');
  });

  it('404 → datasource_missing on signal', () => {
    const err = new AxiosError(
      'Request failed with status code 404',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 404,
        statusText: 'Not Found',
        headers: {},
        config: {} as never,
        data: {},
      },
    );
    expect(classifyWidgetQueryError(err)).toBe('datasource_missing');
  });

  it('does not force data_load codes for unclassified / chart-format failures', () => {
    expect(classifyWidgetQueryError(new Error('chart format mismatch'))).toBe(
      undefined,
    );
    expect(
      classifyWidgetQueryError(
        new AxiosError(
          'Request failed with status code 400',
          'ERR_BAD_REQUEST',
          undefined,
          undefined,
          {
            status: 400,
            statusText: 'Bad Request',
            headers: {},
            config: {} as never,
            data: { message: 'bad query' },
          },
        ),
      ),
    ).toBeUndefined();

    const signal = buildDashboardRenderSignal(
      8,
      ['w1'],
      new Map([
        [
          'w1',
          {
            widgetId: 'w1',
            status: 'failed',
            error: 'dataCannotRenderAsChart',
          },
        ],
      ]),
    );
    expect(signal?.type).toBe('report-failed');
    expect(signal).not.toHaveProperty('errorCode');
  });

  it('axios isAxiosError timeout via plain object path', () => {
    // Ensure classify uses axios.isAxiosError (not only instanceof AxiosError)
    const err = Object.assign(new Error('timeout of 10ms exceeded'), {
      isAxiosError: true,
      code: 'ECONNABORTED',
      name: 'AxiosError',
      toJSON: () => ({}),
    });
    expect(axios.isAxiosError(err)).toBe(true);
    expect(classifyWidgetQueryError(err)).toBe('widget_query_timeout');
  });
});
