import React, { useState, forwardRef, useImperativeHandle, useRef, useEffect } from 'react';
import { Form, Input, message, Switch, Alert, Skeleton } from 'antd';
import { createPortal } from 'react-dom';
import type { FormInstance } from 'antd';
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useSecurityApi } from '@/app/system-manager/api/security';

export interface PasswordModalRef {
  showModal: (config: { userId: string }) => void;
}

const PasswordModal = forwardRef<PasswordModalRef, { onSuccess: () => void }>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [userId, setUserId] = useState('');
    const [password, setPassword] = useState('');
    const [isFocused, setIsFocused] = useState(false);
    const [rulesLoading, setRulesLoading] = useState(true);
    const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });
    const passwordInputRef = useRef<HTMLDivElement>(null);
    const formRef = useRef<FormInstance>(null);
    const { setUserPassword } = useUserApi();
    const { getSystemSettings } = useSecurityApi();

    // 密码规则状态
    const [minLength, setMinLength] = useState<number>(8);
    const [maxLength, setMaxLength] = useState<number>(20);
    const [requiredCharTypes, setRequiredCharTypes] = useState<string[]>([]);

    // 密码验证状态
    const [validationStatus, setValidationStatus] = useState({
      length: false,
      uppercase: false,
      lowercase: false,
      digit: false,
      special: false,
    });

    useEffect(() => {
      if (visible) {
        fetchPasswordRules();
      }
    }, [visible]);

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

    const validatePassword = (pwd: string) => {
      const status = {
        length: pwd.length >= minLength && pwd.length <= maxLength,
        uppercase: /[A-Z]/.test(pwd),
        lowercase: /[a-z]/.test(pwd),
        digit: /[0-9]/.test(pwd),
        special: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(pwd),
      };
      setValidationStatus(status);
      return status;
    };

    const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const pwd = e.target.value;
      setPassword(pwd);
      validatePassword(pwd);
      updateTooltipPosition();
    };

    const updateTooltipPosition = () => {
      if (passwordInputRef.current) {
        const rect = passwordInputRef.current.getBoundingClientRect();
        setTooltipPosition({
          top: rect.top,
          left: rect.left - 200,
        });
      }
    };

    const handleFocus = () => {
      setIsFocused(true);
      updateTooltipPosition();
    };

    useImperativeHandle(ref, () => ({
      showModal: ({ userId }) => {
        setUserId(userId);
        setVisible(true);
        setPassword('');
        setIsFocused(false);
        setRulesLoading(true);
        setValidationStatus({
          length: false,
          uppercase: false,
          lowercase: false,
          digit: false,
          special: false,
        });
        formRef.current?.resetFields();
      },
    }));

    const handleCancel = () => {
      setVisible(false);
    };

    const renderValidationItem = (key: keyof typeof validationStatus, label: string, required: boolean) => {
      if (!required && key !== 'length') return null;
      const isValid = validationStatus[key];
      return (
        <div className="flex items-center gap-2 font-mini mb-2">
          {isValid ? (
            <CheckCircleFilled style={{ color: '#10b981', fontSize: '12px' }} />
          ) : (
            <CloseCircleFilled style={{ color: '#ef4444', fontSize: '12px' }} />
          )}
          <span style={{ color: isValid ? '#059669' : '#dc2626', fontWeight: 500 }}>{label}</span>
        </div>
      );
    };

    const handleConfirm = async () => {
      try {
        setIsSubmitting(true);
        const values = await formRef.current?.validateFields();
        await setUserPassword({ id: userId, password: values.password, temporary: values.temporary ?? false });
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
      <OperateModal
        title={t('system.user.passwordTitle')}
        visible={visible}
        onCancel={handleCancel}
        onOk={handleConfirm}
        confirmLoading={isSubmitting}
        width={700}
      >
        {/* 密码规则提示 */}
        {(rulesLoading ? (
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
        )) as any}

        <Form layout="vertical" ref={formRef as any}>
          <Form.Item
            name="password"
            label={t('system.user.form.password')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <div ref={passwordInputRef}>
              <Input.Password
                placeholder={`${t('common.inputMsg')}${t('system.user.form.password')}`}
                onChange={handlePasswordChange}
                onFocus={handleFocus}
                onBlur={() => setIsFocused(false)}
              />
            </div>
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label={t('system.user.form.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('common.inputRequired') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(
                    new Error(t('system.user.form.passwordMismatch'))
                  );
                },
              }),
            ]}
          >
            <Input.Password placeholder={`${t('common.inputMsg')}${t('system.user.form.confirmPassword')}`} />
          </Form.Item>
          <Form.Item
            name="temporary"
            label={t('system.user.form.temporary')}
            valuePropName="checked"
            tooltip={t('system.user.form.tempTooltip')}>
            <Switch size="small" />
          </Form.Item>
        </Form>

        {/* 使用 Portal 渲染悬浮提示框到 body */}
        {isFocused && password && typeof window !== 'undefined' && createPortal(
          <div 
            className="fixed w-48 bg-[var(--color-bg)] shadow-2xl p-4 rounded-lg"
            style={{
              top: `${tooltipPosition.top}px`,
              left: `${tooltipPosition.left}px`,
              zIndex: 9999,
            }}
          >
            <div className="font-semibold text-xs mb-3 text-[var(--color-text-1)] border-b border-[var(--color-border-1)] pb-2">{t('system.user.passwordValidation')}</div>
            {renderValidationItem('length', `${t('system.security.passwordLengthRange')}: ${minLength}-${maxLength}`, true)}
            {renderValidationItem('uppercase', t('system.security.requireUppercase'), requiredCharTypes.includes('uppercase'))}
            {renderValidationItem('lowercase', t('system.security.requireLowercase'), requiredCharTypes.includes('lowercase'))}
            {renderValidationItem('digit', t('system.security.requireDigit'), requiredCharTypes.includes('digit'))}
            {renderValidationItem('special', t('system.security.requireSpecial'), requiredCharTypes.includes('special'))}
          </div>,
          document.body
        )}
      </OperateModal>
    );
  }
);

PasswordModal.displayName = 'PasswordModal';
export default PasswordModal;
