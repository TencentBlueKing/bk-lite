import React, { useEffect, useRef, useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Form, Input } from 'antd';
import type { FormInstance } from 'antd';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';

import OperateModal from '..';

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

function EditFormModalHarness() {
  const formRef = useRef<FormInstance>(null);
  const [open, setOpen] = useState(false);
  const [formData, setFormData] = useState<{ name: string }>({ name: '' });

  useEffect(() => {
    if (!open) {
      return;
    }
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue(formData);
  }, [formData, open]);

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setFormData({ name: 'NATS_ADMIN_PASSWORD' });
          setOpen(true);
        }}
      >
        edit
      </button>
      <OperateModal footer={null} open={open} title="编辑">
        <Form layout="vertical" ref={formRef}>
          <Form.Item label="名称" name="name">
            <Input placeholder="请输入" />
          </Form.Item>
        </Form>
      </OperateModal>
    </>
  );
}

describe('OperateModal form fill on first open', () => {
  it('回填编辑值，即使这是弹窗第一次打开', async () => {
    const user = userEvent.setup();
    render(<EditFormModalHarness />);

    await user.click(screen.getByRole('button', { name: 'edit' }));

    await waitFor(() => {
      expect(
        (screen.getByLabelText('名称') as HTMLInputElement).value
      ).toBe('NATS_ADMIN_PASSWORD');
    });
  });
});
