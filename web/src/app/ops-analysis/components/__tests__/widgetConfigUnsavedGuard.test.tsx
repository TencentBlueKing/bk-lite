import React, { useEffect } from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Form, Input } from 'antd';
import type { FormInstance } from 'antd';

import DateRangeSelector from '@/app/ops-analysis/components/dateRangeSelector';
import { markFormPristine } from '@/utils/formPristine';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

describe('markFormPristine', () => {
  it('clears touched flags introduced by setFieldsValue after fields are mounted', async () => {
    let formRef: FormInstance | undefined;
    const Probe = () => {
      const [form] = Form.useForm();
      formRef = form;
      useEffect(() => {
        form.setFieldsValue({ name: '组件 A', description: 'desc' });
        markFormPristine(form);
      }, [form]);
      return (
        <Form form={form}>
          <Form.Item name="name">
            <Input />
          </Form.Item>
          <Form.Item name="description">
            <Input />
          </Form.Item>
        </Form>
      );
    };

    render(<Probe />);
    await waitFor(() => {
      expect(formRef?.getFieldValue('name')).toBe('组件 A');
    });
    expect(formRef?.isFieldsTouched()).toBe(false);
  });

  it('still reports dirty after a real user edit', async () => {
    let formRef: FormInstance | undefined;
    const Probe = () => {
      const [form] = Form.useForm();
      formRef = form;
      useEffect(() => {
        form.setFieldsValue({ name: '组件 A' });
        markFormPristine(form);
      }, [form]);
      return (
        <Form form={form}>
          <Form.Item name="name">
            <Input />
          </Form.Item>
        </Form>
      );
    };

    render(<Probe />);
    await waitFor(() => {
      expect(formRef?.isFieldsTouched()).toBe(false);
    });

    const input = document.querySelector('input') as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, '组件 B');
    expect(formRef?.isFieldsTouched()).toBe(true);
  });
});

describe('DateRangeSelector mount side effects', () => {
  it('does not mark the form touched when value is undefined on mount', async () => {
    let formRef: FormInstance | undefined;
    const Probe = () => {
      const [form] = Form.useForm();
      formRef = form;
      return (
        <Form form={form}>
          <Form.Item name={['params', 'range']}>
            <DateRangeSelector />
          </Form.Item>
        </Form>
      );
    };

    render(<Probe />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(formRef?.isFieldsTouched()).toBe(false);
  });
});
