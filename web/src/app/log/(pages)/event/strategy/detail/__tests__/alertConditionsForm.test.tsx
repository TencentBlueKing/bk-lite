import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/log/components/log-query-input', () => ({
  default: () => <input data-testid="log-query" />,
}));

import AlertConditionsForm from '../alertConditionsForm';

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

const Harness = () => {
  const [form] = Form.useForm();
  return (
    <Form form={form}>
      <AlertConditionsForm
        policyType="aggregate"
        unit="min"
        periodUnit="min"
        conditions={[{ func: 'count', field: '_msg', op: '>', value: '1' }]}
        term="and"
        fieldList={['service']}
        logGroups={[]}
        streamList={[]}
        onUnitChange={vi.fn()}
        onPeriodUnitChange={vi.fn()}
        onConditionsChange={vi.fn()}
        onTermChange={vi.fn()}
      />
    </Form>
  );
};

describe('无数据告警开关', () => {
  it('打开开关后出现级别，关闭时隐藏', () => {
    render(<Harness />);

    expect(screen.getByText('log.event.noDataAlert')).toBeTruthy();
    expect(screen.getByText('log.event.noDataTip')).toBeTruthy();
    expect(screen.queryByText('log.event.noDataLevel')).toBeNull();

    fireEvent.click(screen.getByRole('switch'));
    expect(screen.getByText('log.event.noDataLevel')).toBeTruthy();
    expect(screen.getAllByText('log.event.warning').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('switch'));
    expect(screen.queryByText('log.event.noDataLevel')).toBeNull();
  });
});
