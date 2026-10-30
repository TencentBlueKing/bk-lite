import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _defaultMessage?: string, values?: { count?: number | string }) => {
      if (key === 'log.event.noDataWindowLine') {
        return `本窗无日志，上一窗 ${values?.count} 条`;
      }
      return key;
    },
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (value: string) => value,
  }),
}));

vi.mock('@/app/log/context/common', () => ({
  useCommon: () => ({ authOrganizations: [] }),
}));

vi.mock('@/app/log/api/event', () => ({
  default: () => ({
    getAlertSnapshots: vi.fn(),
  }),
}));

vi.mock('@/app/log/hooks/event', () => ({
  useLevelList: () => [],
}));

vi.mock('@/components/custom-table', () => ({
  default: () => <div data-testid="raw-table" />,
}));

vi.mock('../alertHandlerActions', () => ({
  default: () => null,
}));

vi.mock('../index.module.scss', () => ({
  default: { information: 'information', level: 'level' },
}));

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

import Information from '../information';

afterEach(() => {
  cleanup();
});

describe('告警详情命中区', () => {
  it('有 conditions 时逐行显示，没有时只保留原日志表', () => {
    const { rerender } = render(
      <Information
        formData={{ alert_type: 'aggregate', status: 'new' }}
        userList={[]}
        rawData={[{ id: 0, service: 'order', count__msg: 180 }]}
        aggregateResult={{
          conditions: [
            {
              func: 'count',
              field: '_msg',
              current: 180,
              baseline: 120,
              value: 50,
              op: '>',
              threshold: '49',
              matched: true,
            },
          ],
        }}
      />,
    );

    expect(screen.getByTestId('aggregate-condition-table')).toBeTruthy();
    expect(screen.getByText('log.event.funcCount')).toBeTruthy();
    expect(screen.getByText('180')).toBeTruthy();
    expect(screen.getByText('120')).toBeTruthy();
    expect(screen.getByText('50')).toBeTruthy();
    expect(screen.getByText('log.event.verdictWouldTrigger')).toBeTruthy();
    expect(screen.getByTestId('raw-table')).toBeTruthy();

    rerender(
      <Information
        formData={{ alert_type: 'aggregate', status: 'new' }}
        userList={[]}
        rawData={[{ id: 0, count__msg: 180 }]}
        aggregateResult={{ count: 180 }}
      />,
    );
    expect(screen.queryByTestId('aggregate-condition-table')).toBeNull();
    expect(screen.getByTestId('raw-table')).toBeTruthy();
  });

  it('无数据告警显示本窗无日志和上一窗条数', () => {
    render(
      <Information
        formData={{ alert_type: 'aggregate', status: 'new' }}
        userList={[]}
        rawData={[]}
        aggregateResult={{
          count: 0,
          no_data: true,
          baseline: { values: { count__msg: 6 } },
        }}
      />,
    );

    expect(screen.getByTestId('aggregate-no-data-line').textContent).toBe('本窗无日志，上一窗 6 条');
    expect(screen.queryByTestId('aggregate-condition-table')).toBeNull();
  });
});
