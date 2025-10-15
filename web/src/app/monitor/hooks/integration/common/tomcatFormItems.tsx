import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/app/monitor/components/password';

const useTomcatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (disabledFormItems: Record<string, boolean> = {}) => {
      return (
        <>
          <Form.Item label={t('monitor.integrations.username')} required>
            <Form.Item
              noStyle
              name="username"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input
                className="w-[300px] mr-[10px]"
                disabled={disabledFormItems.username}
              />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.usernameDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.password')} required>
            <Form.Item
              noStyle
              name="ENV_PASSWORD"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Password
                className="w-[300px] mr-[10px]"
                disabled={disabledFormItems.password}
              />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.passwordDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { useTomcatFormItems };
