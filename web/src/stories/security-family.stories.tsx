import React from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import { Form } from 'antd';
import AuthSecretField from '@/components/auth-secret-field';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import Password from '@/components/password';
import SectionHeader from '@/components/section-header';
import PasswordFields from '@/components/security/password-fields';
import PasswordFormModal from '@/components/security/password-form-modal';
import PasswordPolicyNotice from '@/components/security/password-policy-notice';
import {
  securityPasswordFieldLabels,
  securityPasswordInputPrefix,
  securityPasswordPolicy,
  securityPasswordValidationHint,
  securityPasswordValidator,
  securityStrictPasswordPolicy,
} from './security-password.fixtures';
import {
  authSecretPrivateKeyFileName,
  authSecretDefaultPassword,
  authSecretPasswordPlaceholder,
  editableSecretDefaultValue,
  editableSecretKeyPlaceholder,
  editableSecretKeyValue,
} from './security-secrets.fixtures';

const SecurityFamilyOverview = () => {
  const [form] = Form.useForm();

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="PasswordPolicyNotice" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <PasswordPolicyNotice
            {...securityStrictPasswordPolicy}
          />
          <PasswordPolicyNotice
            loading
            {...securityStrictPasswordPolicy}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="PasswordFields" titleClassName="text-sm font-semibold" />
        <Form
          form={form}
          layout="vertical"
          initialValues={{ temporary: true }}
          style={{ maxWidth: 480 }}
        >
          <PasswordFields
            labels={securityPasswordFieldLabels}
            passwordInputPrefix={securityPasswordInputPrefix}
            passwordValidator={securityPasswordValidator}
            showTemporaryToggle
          />
        </Form>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Secret leaf inputs"
          titleClassName="text-sm font-semibold"
          description="Security also governs reusable secret-entry leaves. `EditablePasswordField` is the base secret input, while `AuthSecretField` layers the password versus private-key switch used by infrastructure and integration workflows."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="EditablePasswordField" titleClassName="text-sm font-semibold" />
            <div className="space-y-3">
              <EditablePasswordField
                value={editableSecretDefaultValue}
                showPrefixIcon
                onChange={() => undefined}
              />
              <EditablePasswordField
                value={editableSecretKeyValue}
                placeholder={editableSecretKeyPlaceholder}
                showPrefixIcon
                onChange={() => undefined}
              />
              <EditablePasswordField
                value="already-set-secret"
                disabled
                onChange={() => undefined}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="AuthSecretField" titleClassName="text-sm font-semibold" />
            <div className="space-y-3">
              <AuthSecretField
                authType="password"
                passwordValue={authSecretDefaultPassword}
                passwordPlaceholder={authSecretPasswordPlaceholder}
                onPasswordChange={() => undefined}
                onPrivateKeyClear={() => undefined}
                onPrivateKeyLoaded={() => undefined}
              />
              <AuthSecretField
                authType="private_key"
                fileName={authSecretPrivateKeyFileName}
                onPasswordChange={() => undefined}
                onPrivateKeyClear={() => undefined}
                onPrivateKeyLoaded={() => undefined}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Password"
          titleClassName="text-sm font-semibold"
          description="`Password` is the governed masked-value input used across quick execution, integration forms, variable editing, and provider configuration. Its Storybook contract belongs to the Security domain rather than a generic data-entry shelf."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Reveal and edit" titleClassName="text-sm font-semibold" />
            <div className="space-y-3">
              <Password
                value="my-secret-password"
                placeholder="Enter password"
              />
              <Password
                value="copy-this-token-abc123"
                allowCopy
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Direct input states" titleClassName="text-sm font-semibold" />
            <div className="space-y-3">
              <Password
                value=""
                clickToEdit={false}
                placeholder="Type password directly"
              />
              <Password
                value="cannot-edit"
                disabled
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Combined modal contract" titleClassName="text-sm font-semibold" />
        <PasswordFormModal {...({} as any)}
          cancelText="Cancel"
          confirmText="Confirm"
          fieldLabels={securityPasswordFieldLabels}
          maxLength={securityPasswordPolicy.maxLength}
          minLength={securityPasswordPolicy.minLength}
          onCancel={() => undefined}
          onSubmit={async () => undefined}
          open={true}
          passwordInputPrefix={securityPasswordInputPrefix}
          passwordValidator={securityPasswordValidator}
          requiredCharTypes={securityPasswordPolicy.requiredCharTypes}
          showTemporaryToggle
          title="Change password"
          {...securityPasswordValidationHint}
        />
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Security/FamilyOverview',
  component: SecurityFamilyOverview,
  parameters: { layout: 'padded' },
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 900, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SecurityFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
