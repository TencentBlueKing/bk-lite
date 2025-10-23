import React from 'react';
import { Form, Input } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useSyslogVectorFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (disabledFormItems: Record<string, boolean> = {}) => {
      return (
        <>
          <Form.Item
            label={t('log.integration.address')}
            required={true}
            name="address"
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input disabled={disabledFormItems.address} />
          </Form.Item>
        </>
      );
    },
  };
};
export { useSyslogVectorFormItems };
