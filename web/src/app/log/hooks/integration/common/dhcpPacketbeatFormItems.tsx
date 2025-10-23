import React from 'react';
import { Form, InputNumber, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';

const useDhcpPacketbeatFormItems = () => {
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
          <Form.Item
            tooltip={t('log.integration.dhcpPortDes')}
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
              suffixIcon={null}
              open={false}
            />
          </Form.Item>
        </>
      );
    },
  };
};

export { useDhcpPacketbeatFormItems };
