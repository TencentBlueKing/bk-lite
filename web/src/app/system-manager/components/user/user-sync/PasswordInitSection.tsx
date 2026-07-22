'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Form, Input, Select } from 'antd';

import type { PasswordInitConfig, PasswordInitMode } from '@/app/system-manager/types/user-sync';

export interface EmailChannelOption {
  id: number;
  name: string;
}

interface PasswordInitSectionProps {
  /** 通知中心可用邮件通道列表(uniform / random 模式下渲染) */
  emailChannels?: EmailChannelOption[];
  /** i18n 函数 */
  t: (key: string, fallback?: string) => string;
}

const FIELD_PATH = ['platform_config', 'password_init'];

/**
 * 用户同步-本地密码初始化方式 section
 *
 * - mode 选择: 本地 useState 状态(避免 Form.useWatch 嵌套 antd Form 时的渲染问题)
 * - onChange: 同时 setMode 本地状态 + form.setFieldValue 同步写回 form
 * - 初次加载: 从 form 读取初始值(useEffect 读一次,避免每次重渲染都覆盖用户操作)
 *
 * 三种模式:
 *  - none    → 仅显示 hint
 *  - uniform → 渲染 统一密码输入 + 风险提示 + 邮件通道
 *  - random  → 渲染 提示文案 + 邮件通道
 */
const PasswordInitSection: React.FC<PasswordInitSectionProps> = ({
  emailChannels = [],
  t,
}) => {
  const form = Form.useFormInstance();
  const [mode, setMode] = useState<PasswordInitMode>('none');
  const [initialized, setInitialized] = useState(false);
  const [uniformPasswordConfigured, setUniformPasswordConfigured] = useState(false);

  useEffect(() => {
    if (initialized) return;
    const initial = form.getFieldValue(FIELD_PATH) as PasswordInitConfig | undefined;
    if (initial?.mode) {
      setMode(initial.mode);
      setUniformPasswordConfigured(
        initial.mode === 'uniform' && initial.uniform_password_configured === true,
      );
    } else {
      form.setFieldValue(FIELD_PATH, { mode: 'none' });
    }
    setInitialized(true);
  }, [form, initialized]);

  const handleModeChange = (newMode: PasswordInitMode) => {
    setMode(newMode);
    const current = (form.getFieldValue(FIELD_PATH) as PasswordInitConfig | undefined) ?? {};
    const next = { ...current, mode: newMode };
    if (newMode !== 'uniform') {
      delete next.uniform_password;
      delete next.uniform_password_configured;
      setUniformPasswordConfigured(false);
    }
    form.setFieldValue(FIELD_PATH, next);
    form.setFields([{ name: FIELD_PATH, errors: [] }]);
  };

  return (
    <div className="mt-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
      <div className="mb-1 text-[var(--color-text)]">
        {t('system.user.userSyncPage.passwordInit.sectionTitle')}
        <span className="ml-1 text-[var(--color-primary)]">*</span>
      </div>
      <div className="flex flex-col gap-2">
        <Select
          value={mode}
          onChange={handleModeChange}
          style={{ width: '100%' }}
          options={[
            { value: 'none', label: t('system.user.userSyncPage.passwordInit.modeNone') },
            { value: 'uniform', label: t('system.user.userSyncPage.passwordInit.modeUniform') },
            { value: 'random', label: t('system.user.userSyncPage.passwordInit.modeRandom') },
          ]}
        />
        <div className="text-xs text-[var(--color-text-3)]">
          {t(
            `system.user.userSyncPage.passwordInit.mode${
              mode.charAt(0).toUpperCase() + mode.slice(1)
            }Hint`,
          )}
        </div>
      </div>

      {mode === 'uniform' && (
        <>
          <div className="mt-4">
            <Form.Item
              name={[...FIELD_PATH, 'uniform_password']}
              label={t('system.user.userSyncPage.passwordInit.uniformPasswordLabel')}
              required={!uniformPasswordConfigured}
              className="mb-0"
              rules={[
                {
                  required: !uniformPasswordConfigured,
                  message: t('system.user.userSyncPage.passwordInit.uniformPasswordPlaceholder'),
                },
              ]}
              extra={
                uniformPasswordConfigured
                  ? t('system.user.userSyncPage.passwordInit.uniformPasswordKeepHint')
                  : undefined
              }
            >
              <Input.Password
                placeholder={t(
                  'system.user.userSyncPage.passwordInit.uniformPasswordPlaceholder',
                )}
              />
            </Form.Item>
          </div>
          <Alert
            className="mt-3"
            type="warning"
            showIcon
            message={t('system.user.userSyncPage.passwordInit.uniformWarning')}
          />
        </>
      )}

      {(mode === 'uniform' || mode === 'random') && (
        <div className="mt-4">
          <Form.Item
            name={[...FIELD_PATH, 'email_channel_id']}
            label={t('system.user.userSyncPage.passwordInit.emailChannelLabel')}
            required
            className="mb-0"
            rules={[
              {
                required: true,
                message: t('system.user.userSyncPage.passwordInit.emailChannelPlaceholder'),
              },
            ]}
          >
            <Select
              placeholder={t(
                'system.user.userSyncPage.passwordInit.emailChannelPlaceholder',
              )}
              options={emailChannels.map((c) => ({ value: c.id, label: c.name }))}
              allowClear
              style={{ width: '100%' }}
            />
          </Form.Item>
        </div>
      )}
    </div>
  );
};

export default PasswordInitSection;
