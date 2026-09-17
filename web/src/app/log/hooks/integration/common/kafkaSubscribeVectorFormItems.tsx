import React from 'react';
import { Form, Input, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const { Option } = Select;

const useKafkaSubscribeVectorFormItems = () => {
  const { t } = useTranslation();
  const offsetOptions = [
    {
      value: 'latest',
      label: t('log.integration.kafkaSubscribeOffsetLatest')
    },
    {
      value: 'earliest',
      label: t('log.integration.kafkaSubscribeOffsetEarliest')
    }
  ];
  const saslMechanisms = ['PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512'];

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems?: Record<string, boolean>;
      } = {}
    ) => {
      const { disabledFormItems = {} } = extra;

      return (
        <>
          <div className="font-semibold mb-[8px]">
            {t('log.integration.kafkaSubscribeConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.kafkaSubscribeConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeTopics')}
                  </span>
                  <Tooltip
                    title={
                      <div className="whitespace-pre-line">
                        {t('log.integration.kafkaSubscribeTopicsHint')}
                      </div>
                    }
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                  <span className="text-red-500 ml-[2px]">*</span>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name="topics"
                  rules={[{ required: true, message: t('common.required') }]}
                >
                  <Select
                    mode="tags"
                    placeholder={t(
                      'log.integration.kafkaSubscribeTopicsPlaceholder'
                    )}
                    disabled={disabledFormItems.topics}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeGroup')}
                  </span>
                  <Tooltip
                    title={
                      <div className="whitespace-pre-line">
                        {t('log.integration.kafkaSubscribeGroupHint')}
                      </div>
                    }
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="group_id">
                  <Input
                    placeholder={t(
                      'log.integration.kafkaSubscribeGroupPlaceholder'
                    )}
                    disabled={disabledFormItems.group_id}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          <div className="font-semibold mb-[8px]">
            {t('log.integration.kafkaSubscribeServerConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.kafkaSubscribeServerConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeBrokers')}
                  </span>
                  <Tooltip
                    title={
                      <div className="whitespace-pre-line">
                        {t('log.integration.kafkaSubscribeBrokersHint')}
                      </div>
                    }
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                  <span className="text-red-500 ml-[2px]">*</span>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name="bootstrap_servers"
                  rules={[{ required: true, message: t('common.required') }]}
                >
                  <Select
                    mode="tags"
                    placeholder={t(
                      'log.integration.kafkaSubscribeBrokersPlaceholder'
                    )}
                    disabled={disabledFormItems.bootstrap_servers}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          <div className="font-semibold mb-[8px]">
            {t('log.integration.kafkaSubscribeAdvancedConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.kafkaSubscribeAdvancedConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeOffset')}
                  </span>
                  <Tooltip title={t('log.integration.kafkaSubscribeOffsetHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="auto_offset_reset">
                  <Select
                    placeholder={t('log.integration.kafkaSubscribeOffset')}
                    disabled={disabledFormItems.auto_offset_reset}
                  >
                    {offsetOptions.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </div>
            </Form.Item>
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeTls')}
                  </span>
                  <Tooltip title={t('log.integration.kafkaSubscribeTlsHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0"
                  name="tls_enabled"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.tls_enabled} />
                </Form.Item>
              </div>
            </Form.Item>
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.kafkaSubscribeSasl')}
                  </span>
                  <Tooltip title={t('log.integration.kafkaSubscribeSaslHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0"
                  name={['sasl', 'enabled']}
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.sasl_enabled} />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.sasl?.enabled !== curValues?.sasl?.enabled
            }
          >
            {({ getFieldValue }) => {
              const saslEnabled = getFieldValue(['sasl', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !saslEnabled ? 'hidden' : ''
                  }`}
                >
                  {saslEnabled && (
                    <>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.kafkaSubscribeSaslMechanism')}
                            </span>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['sasl', 'mechanism']}
                          >
                            <Select
                              disabled={disabledFormItems.sasl_mechanism}
                            >
                              {saslMechanisms.map((item) => (
                                <Option key={item} value={item}>
                                  {item}
                                </Option>
                              ))}
                            </Select>
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.kafkaSubscribeSaslUsername')}
                            </span>
                            <span className="text-red-500 ml-[2px]">*</span>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['sasl', 'username']}
                            rules={[
                              { required: true, message: t('common.required') }
                            ]}
                          >
                            <Input
                              disabled={disabledFormItems.sasl_username}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.kafkaSubscribeSaslPassword')}
                            </span>
                            <span className="text-red-500 ml-[2px]">*</span>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['sasl', 'password']}
                            rules={[
                              { required: true, message: t('common.required') }
                            ]}
                          >
                            <Input.Password
                              disabled={disabledFormItems.sasl_password}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                    </>
                  )}
                </div>
              );
            }}
          </Form.Item>
        </>
      );
    }
  };
};

export { useKafkaSubscribeVectorFormItems };
