import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import PasswordFormModal from '@/components/security/password-form-modal';
import {
  createPasswordFieldLabels,
  createPasswordValidationRuleLabels,
} from '@/components/security/password-form-modal/presets';
import {
  type PasswordPolicySettings,
  usePasswordPolicy,
} from '@/components/security/password-policy/usePasswordPolicy';

export interface PasswordModalRef {
  showModal: (config: { userId: string }) => void;
}

interface PasswordModalProps {
  onSuccess: () => void;
  fetchSystemSettings: () => Promise<PasswordPolicySettings>;
  setUserPasswordAction: (params: {
    id: string;
    password: string;
    temporary: boolean;
  }) => Promise<unknown>;
}

const PasswordModal = forwardRef<PasswordModalRef, PasswordModalProps>(
  ({ onSuccess, fetchSystemSettings, setUserPasswordAction }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [userId, setUserId] = useState('');
    const {
      minLength,
      maxLength,
      requiredCharTypes,
      resetValidation,
      rulesLoading,
      updateValidationStatus,
      validationStatus,
    } = usePasswordPolicy({
      enabled: visible,
      fetchPolicy: fetchSystemSettings,
    });

    useImperativeHandle(ref, () => ({
      showModal: ({ userId }) => {
        setUserId(userId);
        setVisible(true);
        resetValidation();
      },
    }));

    const handleCancel = () => {
      setVisible(false);
    };

    const handleSubmit = async (values: Record<string, unknown>) => {
      try {
        setIsSubmitting(true);
        await setUserPasswordAction({
          id: userId,
          password: String(values.password ?? ''),
          temporary: Boolean(values.temporary ?? false),
        });
        message.success(t('common.updateSuccess'));
        onSuccess();
        setVisible(false);
      } catch {
        message.error(t('common.operationFailed'));
      } finally {
        setIsSubmitting(false);
      }
    };

    return (
      <PasswordFormModal
        cancelText={t('common.cancel')}
        confirmLoading={isSubmitting}
        confirmText={t('common.confirm')}
        fieldLabels={createPasswordFieldLabels({
          passwordLabel: t('system.user.form.password'),
          passwordPlaceholder: `${t('common.inputMsg')}${t('system.user.form.password')}`,
          confirmLabel: t('system.user.form.confirmPassword'),
          confirmPlaceholder: `${t('common.inputMsg')}${t('system.user.form.confirmPassword')}`,
          requiredMessage: t('common.inputRequired'),
          mismatchMessage: t('system.user.form.passwordMismatch'),
          temporaryLabel: t('system.user.form.temporary'),
          temporaryTooltip: t('system.user.form.tempTooltip'),
        })}
        initialValues={{ temporary: false }}
        maxLength={maxLength}
        minLength={minLength}
        onCancel={handleCancel}
        onPasswordValueChange={updateValidationStatus as unknown as (password: string) => void}
        onSubmit={handleSubmit}
        open={visible}
        passwordValidator={async () => undefined}
        policyLoading={rulesLoading}
        requiredCharTypes={requiredCharTypes}
        showTemporaryToggle
        width={700}
        title={t('system.user.passwordTitle')}
        validationHintTitle={t('system.user.passwordValidation')}
        validationRuleLabels={createPasswordValidationRuleLabels({
          length: `${t('system.security.passwordLengthRange')}: ${minLength}-${maxLength}`,
          uppercase: t('system.security.requireUppercase'),
          lowercase: t('system.security.requireLowercase'),
          digit: t('system.security.requireDigit'),
          special: t('system.security.requireSpecial'),
        })}
        validationStatus={validationStatus}
      />
    );
  }
);

PasswordModal.displayName = 'PasswordModal';
export default PasswordModal;
