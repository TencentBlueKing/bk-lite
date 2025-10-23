import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Password from '@/components/password';

const useDb2ExporterFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (mode?: 'manual' | 'auto' | 'edit') => {
      return (
        <>
          <Form.Item label={t('monitor.integrations.username')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}DATABASE_USER`}
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
              name={`${mode === 'auto' ? 'ENV_' : ''}DATABASE_PASSWORD`}
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
          <Form.Item label={t('monitor.integrations.dbName')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}DATABASE_NAME`}
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
              {t('monitor.integrations.dbNameDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.lcAll')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}LC_ALL`}
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
              {t('monitor.integrations.lcAllDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.lang')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}LANG`}
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
              {t('monitor.integrations.langDes')}
            </span>
          </Form.Item>
          <Form.Item label={t('monitor.integrations.libraryPath')} required>
            <Form.Item
              noStyle
              name={`${mode === 'auto' ? 'ENV_' : ''}LD_LIBRARY_PATH`}
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
              {t('monitor.integrations.libraryPathDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { useDb2ExporterFormItems };
