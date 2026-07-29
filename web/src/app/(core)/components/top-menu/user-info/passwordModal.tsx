'use client';

import React, { useState } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import PasswordFormModal from '@/components/security/password-form-modal';
import {
  createPasswordFieldLabels,
  passwordLockInputPrefix,
} from '@/components/security/password-form-modal/presets';
import { usePasswordPolicy } from '@/components/security/password-policy/usePasswordPolicy';

interface PasswordModalProps {
  visible: boolean;
  onCancel: () => void;
  onSuccess: () => void;
  fetchPolicyAction?: () => Promise<{
    pwd_set_required_char_types?: string | string[];
    pwd_set_min_length?: string;
    pwd_set_max_length?: string;
  }>;
  resetPasswordAction?: (payload: { password: unknown }) => Promise<unknown>;
}

const PasswordModal: React.FC<PasswordModalProps> = ({
  visible,
  onCancel,
  onSuccess,
  fetchPolicyAction,
  resetPasswordAction,
}) => {
  const { t } = useTranslation();
  const { get, post } = useApiClient();
  const [loading, setLoading] = useState(false);
  const {
    minLength,
    maxLength,
    requiredCharTypes,
    rulesLoading,
    validatePassword,
  } = usePasswordPolicy({
    enabled: visible,
    fetchPolicy: () =>
      fetchPolicyAction
        ? fetchPolicyAction()
        : get('/system_mgmt/system_settings/get_sys_set/'),
  });

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      setLoading(true);
      const payload = {
        password: values.newPassword,
      };
      if (resetPasswordAction) {
        await resetPasswordAction(payload);
      } else {
        await post('/console_mgmt/reset_pwd/', payload);
      }
      message.success(t('common.updateSuccess'));
      onSuccess();
    } catch {
      message.error(t('common.updateFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <PasswordFormModal
      cancelText={t('common.cancel')}
      confirmLoading={loading}
      confirmText={t('common.confirm')}
      fieldLabels={createPasswordFieldLabels({
        passwordLabel: t('userInfo.newPassword'),
        passwordPlaceholder: t('userInfo.enterNewPassword'),
        confirmLabel: t('userInfo.confirmPassword'),
        confirmPlaceholder: t('userInfo.enterConfirmPassword'),
        requiredMessage: t('userInfo.enterNewPassword'),
        mismatchMessage: t('userInfo.passwordMismatch'),
      })}
      fieldNames={{ password: 'newPassword' }}
      maxLength={maxLength}
      minLength={minLength}
      onCancel={onCancel}
      onSubmit={handleSubmit}
      open={visible}
      passwordInputPrefix={passwordLockInputPrefix}
      passwordValidator={validatePassword}
      policyLoading={rulesLoading}
      requiredCharTypes={requiredCharTypes}
      title={t('userInfo.changePassword')}
    />
  );
};

export default PasswordModal;
