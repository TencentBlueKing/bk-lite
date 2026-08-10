'use client';

import React from 'react';
import { Form, Input, Switch } from 'antd';

interface PasswordFieldLabels {
  confirmLabel: string;
  confirmPlaceholder: string;
  mismatchMessage: string;
  passwordLabel: string;
  passwordPlaceholder: string;
  requiredMessage: string;
  temporaryLabel?: string;
  temporaryTooltip?: string;
}

interface PasswordFieldNames {
  confirm: string;
  password: string;
  temporary?: string;
}

interface PasswordFieldsProps {
  confirmDependencies?: string[];
  labels: PasswordFieldLabels;
  names?: Partial<PasswordFieldNames>;
  onPasswordBlur?: () => void;
  onPasswordChange?: React.ChangeEventHandler<HTMLInputElement>;
  onPasswordFocus?: () => void;
  passwordInputPrefix?: React.ReactNode;
  passwordValidator: (value: string) => Promise<void>;
  passwordWrapperRef?: React.Ref<HTMLDivElement>;
  showTemporaryToggle?: boolean;
}

const DEFAULT_NAMES: PasswordFieldNames = {
  confirm: 'confirmPassword',
  password: 'password',
  temporary: 'temporary',
};

const PasswordFields: React.FC<PasswordFieldsProps> = ({
  confirmDependencies,
  labels,
  names,
  onPasswordBlur,
  onPasswordChange,
  onPasswordFocus,
  passwordInputPrefix,
  passwordValidator,
  passwordWrapperRef,
  showTemporaryToggle = false,
}) => {
  const resolvedNames = {
    ...DEFAULT_NAMES,
    ...names,
  };

  return (
    <>
      <Form.Item
        name={resolvedNames.password}
        label={labels.passwordLabel}
        rules={[
          { required: true, message: labels.requiredMessage },
          { validator: async (_, value) => passwordValidator(value) },
        ]}
      >
        <div ref={passwordWrapperRef}>
          <Input.Password
            prefix={passwordInputPrefix}
            placeholder={labels.passwordPlaceholder}
            autoComplete="new-password"
            onChange={onPasswordChange}
            onFocus={onPasswordFocus}
            onBlur={onPasswordBlur}
          />
        </div>
      </Form.Item>

      <Form.Item
        name={resolvedNames.confirm}
        label={labels.confirmLabel}
        dependencies={confirmDependencies || [resolvedNames.password]}
        rules={[
          { required: true, message: labels.requiredMessage },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue(resolvedNames.password) === value) {
                return Promise.resolve();
              }
              return Promise.reject(new Error(labels.mismatchMessage));
            },
          }),
        ]}
      >
        <Input.Password
          prefix={passwordInputPrefix}
          placeholder={labels.confirmPlaceholder}
          autoComplete="confirm-password"
        />
      </Form.Item>

      {showTemporaryToggle && resolvedNames.temporary ? (
        <Form.Item
          name={resolvedNames.temporary}
          label={labels.temporaryLabel}
          valuePropName="checked"
          tooltip={labels.temporaryTooltip}
        >
          <Switch size="small" />
        </Form.Item>
      ) : null}
    </>
  );
};

export default PasswordFields;
