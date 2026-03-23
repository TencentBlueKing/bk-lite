import React from 'react';
import { Form, Select, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const useKafkaFilebeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems?: Record<string, boolean>;
        hiddenFormItems?: Record<string, boolean>;
      } = {}
    ) => {
      const { disabledFormItems = {} } = extra;

      return (
        <>
          {/* Kafka Log Section - 开关隐藏，默认为true */}
          <Form.Item noStyle name={['log', 'enabled']} initialValue={true}>
            <input type="hidden" />
          </Form.Item>
          <div className="font-semibold mb-[8px]">
            {t('log.integration.kafkaLog')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.kafkaLogDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] mr-[10px]">
                  <span>{t('log.integration.logPath')}</span>
                  <span className="text-red-500 ml-[2px]">*</span>
                  <Tooltip title={t('log.integration.kafkaLogPathHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name={['log', 'paths']}
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <Select
                    mode="tags"
                    placeholder="/var/log/kafka/server.log"
                    disabled={disabledFormItems.log_paths}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>
        </>
      );
    }
  };
};

export { useKafkaFilebeatFormItems };
