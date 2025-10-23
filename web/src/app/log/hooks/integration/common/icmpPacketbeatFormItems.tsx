import React from 'react';
import { Form, InputNumber } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useIcmpPacketbeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: () => {
      return (
        <>
          <Form.Item
            name="sample_rate"
            label={t('log.integration.sampleRate')}
            tooltip={t('log.integration.sampleRateDes')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <InputNumber
              className="w-full"
              placeholder={t('log.integration.sampleRate')}
              min={0}
              max={1}
            />
          </Form.Item>
        </>
      );
    },
  };
};

export { useIcmpPacketbeatFormItems };
