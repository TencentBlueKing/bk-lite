import React from 'react';
import { Form, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const useNginxFilebeatFormItems = () => {
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
          {/* Access Log Section */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.accessLog')}
              </span>
              <Form.Item noStyle name={['access_log', 'enabled']}>
                <Switch disabled={disabledFormItems.access_log_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.nginxAccessLogDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.access_log?.enabled !== curValues?.access_log?.enabled
            }
          >
            {({ getFieldValue }) => {
              const accessLogEnabled = getFieldValue(['access_log', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !accessLogEnabled ? 'hidden' : ''
                  }`}
                >
                  {accessLogEnabled && (
                    <Form.Item className="mb-0">
                      <div className="flex items-center">
                        <div className="flex items-center w-[100px] mr-[10px]">
                          <span>{t('log.integration.logPath')}</span>
                          <span className="text-red-500 ml-[2px]">*</span>
                          <Tooltip
                            title={t('log.integration.nginxAccessLogPathHint')}
                          >
                            <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                          </Tooltip>
                        </div>
                        <Form.Item
                          className="mb-0 flex-1"
                          name={['access_log', 'paths']}
                          rules={[
                            {
                              required: true,
                              message: t('common.required')
                            }
                          ]}
                        >
                          <Select
                            mode="tags"
                            placeholder="/var/log/nginx/access.log"
                            disabled={disabledFormItems.access_log_paths}
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

          {/* Error Log Section */}
          {!hiddenFormItems.error_log && (
            <>
              <Form.Item layout="vertical" className="mb-[8px]">
                <div className="flex items-center">
                  <span className="mr-[10px] font-semibold">
                    {t('log.integration.errorLog')}
                  </span>
                  <Form.Item noStyle name={['error_log', 'enabled']}>
                    <Switch disabled={disabledFormItems.error_log_enabled} />
                  </Form.Item>
                </div>
              </Form.Item>
              <div className="text-[var(--color-text-3)] mb-[12px]">
                {t('log.integration.nginxErrorLogDesc')}
              </div>
              <Form.Item
                className="mb-[0]"
                shouldUpdate={(prevValues, curValues) =>
                  prevValues?.error_log?.enabled !==
                  curValues?.error_log?.enabled
                }
              >
                {({ getFieldValue }) => {
                  const errorLogEnabled = getFieldValue([
                    'error_log',
                    'enabled'
                  ]);
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
                                title={t(
                                  'log.integration.nginxErrorLogPathHint'
                                )}
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
                                placeholder="/var/log/nginx/error.log"
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
            </>
          )}

          {/* Ingress Controller Log Section */}
          {!hiddenFormItems.ingress_controller && (
            <>
              <Form.Item layout="vertical" className="mb-[8px]">
                <div className="flex items-center">
                  <span className="mr-[10px] font-semibold">
                    {t('log.integration.ingressControllerLog')}
                  </span>
                  <Form.Item noStyle name={['ingress_controller', 'enabled']}>
                    <Switch
                      disabled={disabledFormItems.ingress_controller_enabled}
                    />
                  </Form.Item>
                </div>
              </Form.Item>
              <div className="text-[var(--color-text-3)] mb-[12px]">
                {t('log.integration.ingressControllerLogDesc')}
              </div>
              <Form.Item
                className="mb-[0]"
                shouldUpdate={(prevValues, curValues) =>
                  prevValues?.ingress_controller?.enabled !==
                  curValues?.ingress_controller?.enabled
                }
              >
                {({ getFieldValue }) => {
                  const ingressControllerEnabled = getFieldValue([
                    'ingress_controller',
                    'enabled'
                  ]);
                  return (
                    <div
                      className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                        !ingressControllerEnabled ? 'hidden' : ''
                      }`}
                    >
                      {ingressControllerEnabled && (
                        <Form.Item className="mb-0">
                          <div className="flex items-center">
                            <div className="flex items-center w-[100px] mr-[10px]">
                              <span>{t('log.integration.logPath')}</span>
                              <span className="text-red-500 ml-[2px]">*</span>
                              <Tooltip
                                title={t(
                                  'log.integration.nginxIngressLogPathHint'
                                )}
                              >
                                <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                              </Tooltip>
                            </div>
                            <Form.Item
                              className="mb-0 flex-1"
                              name={['ingress_controller', 'paths']}
                              rules={[
                                {
                                  required: true,
                                  message: t('common.required')
                                }
                              ]}
                            >
                              <Select
                                mode="tags"
                                placeholder="/var/log/nginx/ingress.log"
                                disabled={
                                  disabledFormItems.ingress_controller_paths
                                }
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

export { useNginxFilebeatFormItems };
