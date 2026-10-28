import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
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

describe('连续满足次数', () => {
  it('缺省 1，上限 5', () => {
    render(<Harness />);

    expect(screen.getByText('log.event.triggerCount')).toBeTruthy();
    expect(screen.getByText('log.event.triggerCountTip')).toBeTruthy();
    const node = screen.getByTestId('trigger-count');
    const input = node.tagName === 'INPUT' ? node : node.querySelector('input');
    expect(input).toBeTruthy();
    expect(input?.getAttribute('aria-valuemax')).toBe('5');
    expect(input?.getAttribute('aria-valuemin')).toBe('1');
    expect(input?.getAttribute('aria-valuenow')).toBe('1');
  });
});
