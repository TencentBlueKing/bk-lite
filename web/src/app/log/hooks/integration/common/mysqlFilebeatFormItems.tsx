import React from 'react';
import { Form, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const useMysqlFilebeatFormItems = () => {
  const { t } = useTranslation();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems?: Record<string, boolean>;
        hiddenFormItems?: Record<string, boolean>;
      } = {}
    ) => {
      const { disabledFormItems = {}, hiddenFormItems = {} } = extra;

      return (
        <>
          {/* Error Log Section */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.mysqlErrorLog')}
              </span>
              <Form.Item noStyle name={['error_log', 'enabled']}>
                <Switch disabled={disabledFormItems.error_log_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.mysqlErrorLogDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.error_log?.enabled !== curValues?.error_log?.enabled
            }
          >
            {({ getFieldValue }) => {
              const errorLogEnabled = getFieldValue(['error_log', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !errorLogEnabled ? 'hidden' : ''
                  }`}
                >
                  {errorLogEnabled && (
                    <Form.Item className="mb-0">
                      <div className="flex items-center">
                        <div className="flex items-center w-[100px] mr-[10px]">
                          <span>{t('log.integration.logPath')}</span>
                          <span className="text-red-500 ml-[2px]">*</span>
                          <Tooltip
                            title={t('log.integration.mysqlErrorLogPathHint')}
                          >
                            <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                          </Tooltip>
                        </div>
                        <Form.Item
                          className="mb-0 flex-1"
                          name={['error_log', 'paths']}
                          rules={[
                            {
                              required: true,
                              message: t('common.required')
                            }
                          ]}
                        >
                          <Select
                            mode="tags"
                            placeholder="/var/log/mysql/error.log"
                            disabled={disabledFormItems.error_log_paths}
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
          {!hiddenFormItems.slowlog && (
            <>
              <Form.Item layout="vertical" className="mb-[8px]">
                <div className="flex items-center">
                  <span className="mr-[10px] font-semibold">
                    {t('log.integration.mysqlSlowLog')}
                  </span>
                  <Form.Item noStyle name={['slowlog', 'enabled']}>
                    <Switch disabled={disabledFormItems.slowlog_enabled} />
                  </Form.Item>
                </div>
              </Form.Item>
              <div className="text-[var(--color-text-3)] mb-[12px]">
                {t('log.integration.mysqlSlowLogDesc')}
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
                        <Form.Item className="mb-0">
                          <div className="flex items-center">
                            <div className="flex items-center w-[100px] mr-[10px]">
                              <span>{t('log.integration.logPath')}</span>
                              <span className="text-red-500 ml-[2px]">*</span>
                              <Tooltip
                                title={t(
                                  'log.integration.mysqlSlowLogPathHint'
                                )}
                              >
                                <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                              </Tooltip>
                            </div>
                            <Form.Item
                              className="mb-0 flex-1"
                              name={['slowlog', 'paths']}
                              rules={[
                                {
                                  required: true,
                                  message: t('common.required')
                                }
                              ]}
                            >
                              <Select
                                mode="tags"
                                placeholder="/var/log/mysql/mysql-slow.log"
                                disabled={disabledFormItems.slowlog_paths}
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
            </>
          )}
        </>
      );
    }
  };
};

export { useMysqlFilebeatFormItems };
