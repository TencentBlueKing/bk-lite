import React from 'react';
import { Form, InputNumber, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TIMEOUT_UNITS } from '@/app/monitor/constants/integration';

const { Option } = Select;

const useZookeeperFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: () => {
      return (
        <>
          <Form.Item required label={t('monitor.integrations.timeout')}>
            <Form.Item
              noStyle
              name="timeout"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <InputNumber
                className="mr-[10px]"
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
            <span className="text-[12px] text-[var(--color-text-3)]">
              {t('monitor.integrations.timeoutDes')}
            </span>
          </Form.Item>
        </>
      );
    },
  };
};
export { useZookeeperFormItems };
