import React from 'react';
import { Form, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useHttpPacketbeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems: Record<string, boolean>;
        hiddenFormItems: Record<string, boolean>;
      } = {
        disabledFormItems: {},
        hiddenFormItems: {},
      }
    ) => {
      return (
        <>
          {!extra.hiddenFormItems.ports && (
            <Form.Item
              tooltip={t('log.integration.portsDes')}
              label={t('log.integration.ports')}
              name="ports"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select
                mode="tags"
                placeholder={t('log.integration.ports')}
                disabled={extra.disabledFormItems.ports}
                suffixIcon={null}
                open={false}
              />
            </Form.Item>
          )}
        </>
      );
    },
  };
};

export { useHttpPacketbeatFormItems };
