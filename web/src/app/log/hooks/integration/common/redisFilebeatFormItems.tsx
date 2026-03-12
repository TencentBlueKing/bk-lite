import React from 'react';
import { Form, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';
import Password from '@/components/password';

const useRedisFilebeatFormItems = () => {
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
          {/* Server Log Section */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.redisServerLog')}
              </span>
              <Form.Item noStyle name={['log', 'enabled']}>
                <Switch disabled={disabledFormItems.log_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.redisServerLogDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.log?.enabled !== curValues?.log?.enabled
            }
          >
            {({ getFieldValue }) => {
              const logEnabled = getFieldValue(['log', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !logEnabled ? 'hidden' : ''
                  }`}
                >
                  {logEnabled && (
                    <Form.Item className="mb-0">
                      <div className="flex items-center">
                        <div className="flex items-center w-[100px] mr-[10px]">
                          <span>{t('log.integration.logPath')}</span>
                          <span className="text-red-500 ml-[2px]">*</span>
                          <Tooltip
                            title={t('log.integration.redisLogPathHint')}
                          >
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
                            placeholder="/var/log/redis/redis-server.log"
                            disabled={disabledFormItems.log_paths}
                            suffixIcon={null}
                            open={false}
                          />
                        </Form.Item>
                      </div>
                    </Form.Item>
                  )}
                </div>
              );
            }}
          </Form.Item>

          {/* Slow Log Section */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.redisSlowLog')}
              </span>
              <Form.Item noStyle name={['slowlog', 'enabled']}>
                <Switch disabled={disabledFormItems.slowlog_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.redisSlowLogDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.slowlog?.enabled !== curValues?.slowlog?.enabled
            }
          >
            {({ getFieldValue }) => {
              const slowlogEnabled = getFieldValue(['slowlog', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !slowlogEnabled ? 'hidden' : ''
                  }`}
                >
                  {slowlogEnabled && (
                    <>
                      <Form.Item className="mb-[16px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] mr-[10px]">
                            <span>{t('log.integration.redisHost')}</span>
                            <span className="text-red-500 ml-[2px]">*</span>
                            <Tooltip title={t('log.integration.redisHostHint')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['slowlog', 'hosts']}
                            rules={[
                              {
                                required: true,
                                message: t('common.required')
                              }
                            ]}
                          >
                            <Select
                              mode="tags"
                              placeholder="localhost:6379"
                              disabled={disabledFormItems.slowlog_hosts}
                              suffixIcon={null}
                              open={false}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] mr-[10px]">
                            <span>{t('log.integration.redisPassword')}</span>
                            <Tooltip
                              title={t('log.integration.redisPasswordHint')}
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['slowlog', 'password']}
                          >
                            <Password
                              placeholder={t(
                                'log.integration.redisPasswordPlaceholder'
                              )}
                              disabled={disabledFormItems.slowlog_password}
                              clickToEdit={false}
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

export { useRedisFilebeatFormItems };
