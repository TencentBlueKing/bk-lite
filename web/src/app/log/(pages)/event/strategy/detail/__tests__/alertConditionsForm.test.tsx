import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form, type FormInstance } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { FilterItem } from '@/app/log/types/integration';

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
  policyType = 'aggregate',
  unit = 'min',
  periodUnit = 'min',
  conditions = [{ func: 'count', field: '_msg', op: '>', value: '1' }],
  term = 'and',
  fieldList = ['service'],
  initialValues,
  formRef,
}: {
  onValuesChange?: (changed: Record<string, unknown>) => void;
  policyType?: 'keyword' | 'aggregate';
  unit?: string;
  periodUnit?: string;
  conditions?: FilterItem[];
  term?: string | null;
  fieldList?: string[];
  initialValues?: Record<string, unknown>;
  formRef?: { current: FormInstance | null };
}) => {
  const [form] = Form.useForm();
  if (formRef) {
    formRef.current = form;
  }
  return (
    <Form form={form} onValuesChange={onValuesChange} initialValues={initialValues}>
      <AlertConditionsForm
        policyType={policyType}
        unit={unit}
        periodUnit={periodUnit}
        conditions={conditions}
        term={term}
        fieldList={fieldList}
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

const showFieldsSelect = () => {
  const label = screen.getByText('log.event.displayFields');
  const select = label.closest('.ant-form-item')?.querySelector('.ant-select');
  if (!select) {
    throw new Error('display fields select missing');
  }
  return select;
};

interface ShowFieldsFiber {
  return?: ShowFieldsFiber | null;
  memoizedProps?: {
    onChange?: (value: string[]) => void;
    value?: unknown;
    mode?: string;
  };
}

const changeShowFields = (next: string[]) => {
  const select = showFieldsSelect();
  const fiberKey = Object.keys(select).find((key) => key.startsWith('__reactFiber$'));
  if (!fiberKey) {
    throw new Error('react fiber missing');
  }
  let fiber = (select as unknown as Record<string, ShowFieldsFiber>)[fiberKey];
  while (fiber) {
    const onChange = fiber.memoizedProps?.onChange;
    if (typeof onChange === 'function' && fiber.memoizedProps?.mode === 'multiple') {
      onChange(next);
      return;
    }
    fiber = fiber.return ?? undefined;
  }
  throw new Error('show fields onChange missing');
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

    fireEvent.change(screen.getAllByPlaceholderText('log.event.enterThreshold')[0], {
      target: { value: '9' },
    });

    expect(onValuesChange).not.toHaveBeenCalled();
  });
});

describe('关键字和聚合说明', () => {
  it('聚合查询说明和连续次数说明用聚合口径', () => {
    render(<Harness policyType="aggregate" />);

    expect(screen.queryByText('log.event.alarmLevel')).toBeNull();
    expect(screen.getByText('log.event.aggregateQueryCriteriaTips')).toBeTruthy();
    expect(screen.getByText('log.event.conditionSection')).toBeTruthy();
    expect(screen.getByText('log.event.levelSection')).toBeTruthy();
    expect(screen.queryByText('log.integration.rule')).toBeNull();
    expect(screen.getByText('log.event.triggerCountTip')).toBeTruthy();
    expect(screen.getByText('log.event.recoverAfter')).toBeTruthy();
    expect(screen.getByTestId('recover-after')).toBeTruthy();
    expect(screen.queryByText('log.event.queryCriteriaTips')).toBeNull();
    expect(screen.queryByText('log.event.minHits')).toBeNull();
  });

  it('关键字用命中条数，不渲染连续次数和规则区', () => {
    render(<Harness policyType="keyword" />);

    expect(screen.getByText('log.event.alarmLevel')).toBeTruthy();
    expect(screen.getByText('log.event.queryCriteriaTips')).toBeTruthy();
    expect(screen.getByText('log.event.minHits')).toBeTruthy();
    expect(screen.getByText('log.event.minHitsTip')).toBeTruthy();
    expect(screen.queryByText('log.event.aggregateQueryCriteriaTips')).toBeNull();
    expect(screen.queryByText('log.event.triggerCount')).toBeNull();
    expect(screen.queryByText('log.event.recoverAfter')).toBeNull();
    expect(screen.queryByText('log.integration.rule')).toBeNull();
    const node = screen.getByTestId('min-hits');
    const input = node.tagName === 'INPUT' ? node : node.querySelector('input');
    expect(input?.getAttribute('aria-valuemin')).toBe('1');
    expect(input?.getAttribute('aria-valuemax')).toBe('100000');
    expect(input?.getAttribute('aria-valuenow')).toBe('1');
  });
});

describe('展示字段和检测周期', () => {
  it('去掉 message 后固定字段仍在，且固定项没有关闭图标', async () => {
    const clientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
    const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
    const getBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => 800,
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
      configurable: true,
      get: () => 80,
    });
    HTMLElement.prototype.getBoundingClientRect = () => ({
      width: 800,
      height: 32,
      top: 0,
      left: 0,
      bottom: 32,
      right: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    try {
      const formRef = { current: null as FormInstance | null };
      render(
        <Harness
          formRef={formRef}
          fieldList={['level', 'service']}
          initialValues={{ show_fields: ['timestamp', 'message', 'level'] }}
        />
      );

      expect(formRef.current?.getFieldValue('show_fields')).toEqual(['timestamp', 'message', 'level']);
      await waitFor(() => {
        expect(screen.getByText('timestamp').closest('.ant-tag')).toBeTruthy();
      });
      for (const field of ['timestamp', 'message']) {
        const tag = screen.getByText(field).closest('.ant-tag');
        expect(tag?.querySelector('.ant-tag-close-icon')).toBeNull();
      }
      expect(screen.getByText('level').closest('.ant-tag')?.querySelector('.ant-tag-close-icon')).toBeTruthy();

      act(() => {
        changeShowFields(['timestamp', 'level']);
      });
      expect(formRef.current?.getFieldValue('show_fields')).toEqual(
        expect.arrayContaining(['timestamp', 'message'])
      );
    } finally {
      if (clientWidth) {
        Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientWidth);
      }
      if (offsetWidth) {
        Object.defineProperty(HTMLElement.prototype, 'offsetWidth', offsetWidth);
      }
      HTMLElement.prototype.getBoundingClientRect = getBoundingClientRect;
    }
  });

  it('频率远稀于周期时提示补扫缺口，频率与周期相同则不提示', () => {
    const { unmount } = render(
      <Harness unit="day" periodUnit="min" initialValues={{ schedule: 1, period: 5 }} />
    );
    expect(screen.getByText('log.event.backfillGapWarning')).toBeTruthy();
    unmount();

    render(<Harness unit="min" periodUnit="min" initialValues={{ schedule: 5, period: 5 }} />);
    expect(screen.queryByText('log.event.backfillGapWarning')).toBeNull();
  });

  it('完整条件的非数值阈值校验失败', async () => {
    const formRef = { current: null as FormInstance | null };
    render(
      <Harness
        formRef={formRef}
        conditions={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: 'abc',
            compare: { kind: 'percent', to: 'previous_window' },
          },
        ]}
        initialValues={{
          log_groups: [1],
          query: 'error',
          show_fields: ['timestamp', 'message'],
          schedule: 5,
          period: 5,
          alert_level: 'warning',
        }}
      />
    );

    let caught: unknown;
    await act(async () => {
      try {
        await formRef.current?.validateFields();
      } catch (error) {
        caught = error;
      }
    });
    expect(caught).toMatchObject({
      errorFields: expect.arrayContaining([
        expect.objectContaining({
          errors: expect.arrayContaining(['log.event.thresholdNumberValidate']),
        }),
      ]),
    });
  });

  it('大于的降序阶梯和 and 级别集合不一致都会被规则拦住', async () => {
    const formRef = { current: null as FormInstance | null };
    const { unmount } = render(
      <Harness
        formRef={formRef}
        term="and"
        conditions={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '50',
            thresholds: [
              { level: 'warning', value: '50' },
              { level: 'error', value: '10' },
            ],
          },
        ]}
        initialValues={{
          log_groups: [1],
          query: 'error',
          show_fields: ['timestamp', 'message'],
          schedule: 5,
          period: 5,
        }}
      />
    );
    let orderError: unknown;
    await act(async () => {
      try {
        await formRef.current?.validateFields();
      } catch (error) {
        orderError = error;
      }
    });
    expect(orderError).toMatchObject({
      errorFields: expect.arrayContaining([
        expect.objectContaining({
          errors: expect.arrayContaining(['log.event.thresholdOrderValidate']),
        }),
      ]),
    });
    unmount();

    const mismatchRef = { current: null as FormInstance | null };
    render(
      <Harness
        formRef={mismatchRef}
        term="and"
        conditions={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '10',
            thresholds: [{ level: 'warning', value: '10' }],
          },
          {
            func: 'count',
            field: 'service',
            op: '>',
            value: '10',
            thresholds: [
              { level: 'warning', value: '10' },
              { level: 'critical', value: '30' },
            ],
          },
        ]}
        initialValues={{
          log_groups: [1],
          query: 'error',
          show_fields: ['timestamp', 'message'],
          schedule: 5,
          period: 5,
        }}
      />
    );
    let mismatch: unknown;
    await act(async () => {
      try {
        await mismatchRef.current?.validateFields();
      } catch (error) {
        mismatch = error;
      }
    });
    expect(mismatch).toMatchObject({
      errorFields: expect.arrayContaining([
        expect.objectContaining({
          errors: expect.arrayContaining(['log.event.levelSetMismatch']),
        }),
      ]),
    });
  });
});
