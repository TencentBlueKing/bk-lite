'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Form } from 'antd';
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import OperateFormModal from '@/components/operate-form-modal';
import PasswordFields from '@/components/security/password-fields';
import PasswordPolicyNotice from '@/components/security/password-policy-notice';
import type { PasswordValidationStatus } from '@/components/security/password-policy/usePasswordPolicy';

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

interface PasswordFormModalProps {
  cancelText: string;
  confirmLoading?: boolean;
  confirmText: string;
  fieldLabels: PasswordFieldLabels;
  fieldNames?: Partial<PasswordFieldNames>;
  initialValues?: Record<string, unknown>;
  maxLength: number;
  minLength: number;
  onCancel: () => void;
  onPasswordValueChange?: (password: string) => void;
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void;
  open: boolean;
  passwordInputPrefix?: React.ReactNode;
  passwordValidator: (value: string) => Promise<void>;
  policyLoading?: boolean;
  requiredCharTypes: readonly string[];
  showTemporaryToggle?: boolean;
  title: React.ReactNode;
  validationRuleLabels?: Partial<Record<keyof PasswordValidationStatus, string>>;
  validationHintTitle?: string;
  validationStatus?: PasswordValidationStatus;
  width?: number;
}

const DEFAULT_FIELD_NAMES: PasswordFieldNames = {
  confirm: 'confirmPassword',
  password: 'password',
  temporary: 'temporary',
};

const VALIDATION_LABEL_KEYS: Array<keyof PasswordValidationStatus> = [
  'length',
  'uppercase',
  'lowercase',
  'digit',
  'special',
];

const PasswordFormModal: React.FC<PasswordFormModalProps> = ({
  cancelText,
  confirmLoading = false,
  confirmText,
  fieldLabels,
  fieldNames,
  initialValues,
  maxLength,
  minLength,
  onCancel,
  onPasswordValueChange,
  onSubmit,
  open,
  passwordInputPrefix,
  passwordValidator,
  policyLoading = false,
  requiredCharTypes,
  showTemporaryToggle = false,
  title,
  validationRuleLabels,
  validationHintTitle,
  validationStatus,
  width = 700,
}) => {
  const [form] = Form.useForm();
  const [isPasswordFocused, setIsPasswordFocused] = useState(false);
  const [passwordValue, setPasswordValue] = useState('');

  const resolvedFieldNames = useMemo(
    () => ({
      ...DEFAULT_FIELD_NAMES,
      ...fieldNames,
    }),
    [fieldNames]
  );

  useEffect(() => {
    if (!open) {
      form.resetFields();
      setPasswordValue('');
      setIsPasswordFocused(false);
      return;
    }

    form.resetFields();
    if (initialValues) {
      form.setFieldsValue(initialValues);
    }
  }, [form, initialValues, open]);

  const validationLabels = useMemo(
    () => ({
      length: validationRuleLabels?.length ?? `Length ${minLength}-${maxLength}`,
      uppercase: validationRuleLabels?.uppercase ?? 'Uppercase letter',
      lowercase: validationRuleLabels?.lowercase ?? 'Lowercase letter',
      digit: validationRuleLabels?.digit ?? 'Number',
      special: validationRuleLabels?.special ?? 'Special character',
    }),
    [maxLength, minLength, validationRuleLabels]
  );

  const handleConfirm = async () => {
    const values = await form.validateFields();
    await onSubmit(values);
  };

  const showValidationHint = Boolean(
    validationHintTitle && validationStatus && isPasswordFocused && passwordValue
  );

  return (
    <OperateFormModal
      title={title}
      open={open}
      onCancel={onCancel}
      width={width}
      confirmText={confirmText}
      cancelText={cancelText}
      onConfirm={handleConfirm}
      confirmLoading={confirmLoading}
      cancelDisabled={confirmLoading}
      primaryFirst={false}
    >
      <PasswordPolicyNotice
        className="mb-4"
        loading={policyLoading}
        minLength={minLength}
        maxLength={maxLength}
        requiredCharTypes={requiredCharTypes}
      />

      <Form form={form} layout="vertical" initialValues={initialValues}>
        <PasswordFields
          labels={fieldLabels}
          names={resolvedFieldNames}
          onPasswordBlur={() => setIsPasswordFocused(false)}
          onPasswordChange={(event) => {
            const nextValue = event.target.value;
            setPasswordValue(nextValue);
            onPasswordValueChange?.(nextValue);
          }}
          onPasswordFocus={() => setIsPasswordFocused(true)}
          passwordInputPrefix={passwordInputPrefix}
          passwordValidator={passwordValidator}
          showTemporaryToggle={showTemporaryToggle}
        />
      </Form>

      {showValidationHint ? (
        <div className="mt-3 rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4">
          <div className="mb-3 text-xs font-semibold text-[var(--color-text-1)]">
            {validationHintTitle}
          </div>
          <div className="grid gap-2">
            {VALIDATION_LABEL_KEYS.map((key) => {
              if (key !== 'length' && !requiredCharTypes.includes(key as string)) {
                return null;
              }

              const isValid = validationStatus?.[key] ?? false;

              return (
                <div key={key} className="flex items-center gap-2 text-xs">
                  {isValid ? (
                    <CheckCircleFilled style={{ color: '#10b981', fontSize: '12px' }} />
                  ) : (
                    <CloseCircleFilled style={{ color: '#ef4444', fontSize: '12px' }} />
                  )}
                  <span style={{ color: isValid ? '#059669' : '#dc2626', fontWeight: 500 }}>
                    {validationLabels[key]}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </OperateFormModal>
  );
};

export default PasswordFormModal;
