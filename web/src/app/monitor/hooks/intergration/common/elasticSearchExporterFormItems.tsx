import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/app/monitor/components/password';

const useElasticSearchExporterFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      disabledFormItems: Record<string, boolean> = {},
      mode?: 'manual' | 'auto' | 'edit'
    ) => {
      return (
        <>
          <Form.Item label={t('monitor.intergrations.username')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}ES_USERNAME`}
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
              {t('monitor.intergrations.usernameDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.intergrations.password')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}ES_PASSWORD`}
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
              {t('monitor.intergrations.passwordDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { useElasticSearchExporterFormItems };
