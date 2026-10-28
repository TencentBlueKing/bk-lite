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

const Harness = ({
  onValuesChange,
}: {
  onValuesChange?: (changed: Record<string, unknown>) => void;
}) => {
  const [form] = Form.useForm();
  return (
    <Form form={form} onValuesChange={onValuesChange}>
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

  it('栏头显示 matchPrefix', () => {
    render(<Harness />);

    expect(screen.getByText('log.event.matchPrefix')).toBeTruthy();
  });

  it('编辑条件不把条件写进表单字段 rule', () => {
    const onValuesChange = vi.fn();
    render(<Harness onValuesChange={onValuesChange} />);

    fireEvent.change(screen.getByPlaceholderText('log.event.enterThreshold'), {
      target: { value: '9' },
    });

    expect(onValuesChange).not.toHaveBeenCalled();
  });
});
