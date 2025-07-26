import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/app/monitor/components/password';

const useGreenPlumExporterFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (mode?: 'manual' | 'auto' | 'edit') => {
      return (
        <>
          <Form.Item label={t('monitor.intergrations.username')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}SQL_EXPORTER_USER`}
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
              {t('monitor.intergrations.usernameDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.intergrations.password')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}SQL_EXPORTER_PASS`}
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
              {t('monitor.intergrations.passwordDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.intergrations.dbName')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}SQL_EXPORTER_DB_NAME`}
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
              {t('monitor.intergrations.dbNameDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { useGreenPlumExporterFormItems };
