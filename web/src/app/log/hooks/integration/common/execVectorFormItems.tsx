import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useExecVectorFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (disabledFormItems: Record<string, boolean> = {}) => {
      return (
        <>
          <Form.Item
            label={t('log.integration.command')}
            required={true}
            name="command"
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input disabled={disabledFormItems.command} />
          </Form.Item>
        </>
      );
    },
  };
};
export { useExecVectorFormItems };
