'use client';

import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Button, message, Spin, Alert, Skeleton } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { useSecurityApi } from '@/app/system-manager/api/security';

interface PasswordModalProps {
    visible: boolean;
    onCancel: () => void;
    onSuccess: () => void;
}

const PasswordModal: React.FC<PasswordModalProps> = ({
  visible,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation();
  const { post } = useApiClient();
  const { getSystemSettings } = useSecurityApi();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  const [minLength, setMinLength] = useState<number>(8);
  const [maxLength, setMaxLength] = useState<number>(20);
  const [requiredCharTypes, setRequiredCharTypes] = useState<string[]>(['uppercase', 'lowercase', 'digit', 'special']);
  const [rulesLoading, setRulesLoading] = useState(true);

  useEffect(() => {
    if (visible) {
      fetchPasswordRules();
    }
  }, [visible]);

  const fetchPasswordRules = async () => {
    try {
      setRulesLoading(true);
      const settings = await getSystemSettings();
      setMinLength(parseInt(settings.pwd_set_min_length || '8'));
      setMaxLength(parseInt(settings.pwd_set_max_length || '20'));

      let types: string[] = ['uppercase', 'lowercase', 'digit', 'special'];
      if (settings.pwd_set_required_char_types) {
        if (typeof settings.pwd_set_required_char_types === 'string') {
          types = settings.pwd_set_required_char_types.split(',').filter(Boolean);
        } else if (Array.isArray(settings.pwd_set_required_char_types)) {
          types = settings.pwd_set_required_char_types;
        }
      }
      setRequiredCharTypes(types);
    } catch (error) {
      console.error('Failed to fetch password rules:', error);
      // 失败时使用默认值
      setRequiredCharTypes(['uppercase', 'lowercase', 'digit', 'special']);
    } finally {
      setRulesLoading(false);
    }
  };

  const handleFinish = async (values: any) => {
    try {
      setLoading(true);
      await post('/console_mgmt/reset_pwd/', {
        password: values.newPassword
      });
      message.success(t('common.updateSuccess'));
      form.resetFields();
      onSuccess();
    } catch {
      console.error(t('common.updateFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    onCancel();
  };

  // 动态密码验证器
  const validatePassword = (value: string) => {
    if (!value) return Promise.resolve();

    // 验证长度
    if (value.length < minLength || value.length > maxLength) {
      return Promise.reject(new Error(`${t('system.security.passwordLengthRange')}: ${minLength}-${maxLength}`));
    }

    // 验证必需的字符类型
    const validations: Record<string, boolean> = {
      uppercase: /[A-Z]/.test(value),
      lowercase: /[a-z]/.test(value),
      digit: /\d/.test(value),
      special: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(value),
    };

    const missingTypes: string[] = [];
    const typeLabels: Record<string, string> = {
      uppercase: t('system.security.requireUppercase'),
      lowercase: t('system.security.requireLowercase'),
      digit: t('system.security.requireDigit'),
      special: t('system.security.requireSpecial'),
    };

    requiredCharTypes.forEach(type => {
      if (!validations[type]) {
        missingTypes.push(typeLabels[type]);
      }
    });

    if (missingTypes.length > 0) {
      return Promise.reject(new Error(`${t('system.security.passwordComplexity')}: ${missingTypes.join('、')}`));
    }

    return Promise.resolve();
  };

  return (
    <Modal
      maskClosable={false}
      centered
      title={t('userInfo.changePassword')}
      open={visible}
      onCancel={handleCancel}
      footer={null}
    >
      <Spin spinning={loading || rulesLoading}>
        {/* 密码规则提示 */}
        {rulesLoading ? (
          <Skeleton active paragraph={{ rows: 2 }} className="mb-4" />
        ) : (
          <Alert
            message={
              <div>
                <div className="font-semibold mb-1">
                  {t('system.security.passwordLengthRange')}: {minLength}-{maxLength}
                </div>
                <div className="text-xs">
                  {t('system.security.passwordComplexity')}: {requiredCharTypes.map(type => {
                    const labels: Record<string, string> = {
                      uppercase: t('system.security.requireUppercase'),
                      lowercase: t('system.security.requireLowercase'),
                      digit: t('system.security.requireDigit'),
                      special: t('system.security.requireSpecial'),
                    };
                    return labels[type];
                  }).join('、')}
                </div>
              </div>
            }
            type="info"
            showIcon
            className="mb-4"
          />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={handleFinish}
        >
          <Form.Item
            label={t('userInfo.newPassword')}
            name="newPassword"
            rules={[
              { required: true, message: t('userInfo.enterNewPassword') },
              { validator: (_, value) => validatePassword(value) },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('userInfo.enterNewPassword')}
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item
            label={t('userInfo.confirmPassword')}
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: t('userInfo.enterConfirmPassword') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('userInfo.passwordMismatch')));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('userInfo.enterConfirmPassword')}
              autoComplete="confirm-password"
            />
          </Form.Item>

          <Form.Item className="mb-0">
            <div className="flex justify-end gap-2">
              <Button onClick={handleCancel}>
                {t('common.cancel')}
              </Button>
              <Button type="primary" htmlType="submit">
                {t('common.confirm')}
              </Button>
            </div>
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  );
};

export default PasswordModal;
