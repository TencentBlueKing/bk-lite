import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { CredentialFieldsBlock } from '../fields';
import type { CredentialFieldSchema } from '../types';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

afterEach(() => {
  cleanup();
});

const PASSWORD: CredentialFieldSchema = {
  id: 'password',
  name: '密码',
  kind: 'secret',
  required: true,
};

function SecretForm({
  requireSecrets,
  formRef,
}: {
  requireSecrets?: boolean;
  formRef: { current: FormInstance | null };
}) {
  const [form] = Form.useForm();
  formRef.current = form;
  return (
    <Form form={form} initialValues={{ fields: {} }}>
      <CredentialFieldsBlock
        fields={[PASSWORD]}
        form={form}
        requireSecrets={requireSecrets}
      />
    </Form>
  );
}

describe('CredentialFieldsBlock secret required', () => {
  it('rejects a blank required secret on create', async () => {
    const formRef: { current: FormInstance | null } = { current: null };
    const { container } = render(<SecretForm requireSecrets formRef={formRef} />);
    expect(container.querySelector('.ant-form-item-required')).toBeTruthy();
    await expect(act(() => formRef.current!.validateFields())).rejects.toMatchObject({
      errorFields: expect.arrayContaining([
        expect.objectContaining({ name: ['fields', 'password'] }),
      ]),
    });
  });

  it('allows a blank required secret when editing (leave blank to keep)', async () => {
    const formRef: { current: FormInstance | null } = { current: null };
    const { container } = render(<SecretForm requireSecrets={false} formRef={formRef} />);
    expect(container.querySelector('.ant-form-item-required')).toBeNull();
    await expect(act(() => formRef.current!.validateFields())).resolves.toEqual({ fields: {} });
  });

  it('does not render a clear-saved-secret control for optional secrets', () => {
    const formRef: { current: FormInstance | null } = { current: null };
    function OptionalSecretForm() {
      const [form] = Form.useForm();
      formRef.current = form;
      return (
        <Form form={form} initialValues={{ fields: {} }}>
          <CredentialFieldsBlock
            fields={[{ id: 'passphrase', name: '私钥口令', kind: 'secret' }]}
            form={form}
            requireSecrets={false}
          />
        </Form>
      );
    }
    render(<OptionalSecretForm />);
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});
