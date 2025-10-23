import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/components/password';

const usePostgresExporterFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (mode?: 'manual' | 'auto' | 'edit') => {
      return (
        <>
          <Form.Item label={t('monitor.integrations.username')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}DATA_SOURCE_USER`}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input className="w-[300px] mr-[10px]" />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.usernameDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.password')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}DATA_SOURCE_PASS`}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Password className="w-[300px] mr-[10px]" />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.passwordDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.dataSource')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}DATA_SOURCE_DB`}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Input className="w-[300px] mr-[10px]" />
            </Form.Item>
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.dataSourceDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { usePostgresExporterFormItems };
