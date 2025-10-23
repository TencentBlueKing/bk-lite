import React from 'react';
import { Form, InputNumber, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TIMEOUT_UNITS } from '@/app/log/constants';
const { Option } = Select;

const useFlowsPacketbeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: () => {
      return (
        <>
          <Form.Item
            name="flows_timeout"
            label={t('log.integration.flowsTimeout')}
            tooltip={t('log.integration.flowsTimeoutDes')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <InputNumber
              className="w-full"
              placeholder={t('log.integration.flowsTimeout')}
              min={1}
              precision={0}
              addonAfter={
                <Select style={{ width: 116 }} defaultValue="s">
                  {TIMEOUT_UNITS.map((item: string) => (
                    <Option key={item} value={item}>
                      {item}
                    </Option>
                  ))}
                </Select>
              }
            />
          </Form.Item>
          <Form.Item
            name="flows_period"
            label={t('log.integration.flowsPeriod')}
            tooltip={t('log.integration.flowsPeriodDes')}
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <InputNumber
              className="w-full"
              placeholder={t('log.integration.flowsPeriod')}
              min={1}
              precision={0}
              addonAfter={
                <Select style={{ width: 116 }} defaultValue="s">
                  {TIMEOUT_UNITS.map((item: string) => (
                    <Option key={item} value={item}>
                      {item}
                    </Option>
                  ))}
                </Select>
              }
            />
          </Form.Item>
        </>
      );
    },
  };
};

export { useFlowsPacketbeatFormItems };
