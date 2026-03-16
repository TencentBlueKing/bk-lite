import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useConditionModeList } from '@/app/log/hooks/integration/common/other';
const { Option } = Select;

const useDockerVectorFormItems = () => {
  const { t } = useTranslation();
  const conditionModeList = useConditionModeList();

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
          {/* 端点 */}
          <Form.Item
            label={
              <span>
                {t('log.integration.endpoint')}
                <Tooltip
                  title={
                    <div style={{ whiteSpace: 'pre-line' }}>
                      {t('log.integration.dockerEndpointTooltip')}
                    </div>
                  }
                >
                  <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                </Tooltip>
              </span>
            }
            required={true}
            name="endpoint"
            rules={[
              {
                required: true,
                message: t('common.required')
              }
            ]}
          >
            <Input
              placeholder="unix:///var/run/docker.sock"
              disabled={disabledFormItems.endpoint}
            />
          </Form.Item>

          {/* 容器过滤条件 */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.dockerContainerFilterCondition')}
              </span>
              <Form.Item noStyle name={['containerFilter', 'enabled']}>
                <Switch disabled={disabledFormItems.containerFilter_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.dockerContainerFilterDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.containerFilter?.enabled !==
              curValues?.containerFilter?.enabled
            }
          >
            {({ getFieldValue }) => {
              const containerFilterEnabled = getFieldValue([
                'containerFilter',
                'enabled'
              ]);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !containerFilterEnabled ? 'hidden' : ''
                  }`}
                >
                  {containerFilterEnabled && (
                    <>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerContainerNameContains')}
                            </span>
                            <Tooltip
                              title={t(
                                'log.integration.dockerContainerNameContainsTooltip'
                              )}
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name="container_name_contains"
                          >
                            <Select
                              mode="tags"
                              placeholder={t(
                                'log.integration.dockerContainerPlaceholder'
                              )}
                              disabled={
                                disabledFormItems.container_name_contains
                              }
                              suffixIcon={null}
                              open={false}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerContainerNameExclude')}
                            </span>
                            <Tooltip
                              title={t(
                                'log.integration.dockerContainerNameExcludeTooltip'
                              )}
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name="container_name_exclude"
                          >
                            <Select
                              mode="tags"
                              placeholder={t(
                                'log.integration.dockerContainerPlaceholder'
                              )}
                              disabled={
                                disabledFormItems.container_name_exclude
                              }
                              suffixIcon={null}
                              open={false}
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

          {/* 日志处理配置 - 多行合并 */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.dockerLogProcessConfig')}
              </span>
              <Form.Item noStyle name={['multiline', 'enabled']}>
                <Switch disabled={disabledFormItems.multiline_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.dockerMultilineMergeDesc')}
          </div>
          <Form.Item
            className="mb-[0]"
            shouldUpdate={(prevValues, curValues) =>
              prevValues?.multiline?.enabled !== curValues?.multiline?.enabled
            }
          >
            {({ getFieldValue }) => {
              const multilineEnabled = getFieldValue(['multiline', 'enabled']);
              return (
                <div
                  className={`bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px] ${
                    !multilineEnabled ? 'hidden' : ''
                  }`}
                >
                  {multilineEnabled && (
                    <>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerMergeMode')}
                            </span>
                            <Tooltip
                              title={
                                <div style={{ whiteSpace: 'pre-line' }}>
                                  {t('log.integration.dockerMergeModeTooltip')}
                                </div>
                              }
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['multiline', 'mode']}
                          >
                            <Select
                              placeholder={t('log.integration.dockerMergeMode')}
                              disabled={disabledFormItems.multiline_mode}
                            >
                              {conditionModeList.map((item) => (
                                <Option key={item.value} value={item.value}>
                                  {item.title}
                                </Option>
                              ))}
                            </Select>
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerMatchRegex')}
                            </span>
                            <Tooltip
                              title={
                                <div style={{ whiteSpace: 'pre-line' }}>
                                  {t('log.integration.dockerMatchRegexTooltip')}
                                </div>
                              }
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['multiline', 'condition_pattern']}
                          >
                            <Input
                              placeholder="^[\s]+"
                              disabled={
                                disabledFormItems.multiline_condition_pattern
                              }
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerStartPattern')}
                            </span>
                            <Tooltip
                              title={
                                <div style={{ whiteSpace: 'pre-line' }}>
                                  {t(
                                    'log.integration.dockerStartPatternTooltip'
                                  )}
                                </div>
                              }
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['multiline', 'start_pattern']}
                          >
                            <Input
                              placeholder="^[^\s]"
                              disabled={
                                disabledFormItems.multiline_start_pattern
                              }
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[120px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.dockerTimeoutMs')}
                            </span>
                            <Tooltip
                              title={t(
                                'log.integration.dockerTimeoutMsTooltip'
                              )}
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            className="mb-0 flex-1"
                            name={['multiline', 'timeout_ms']}
                          >
                            <InputNumber
                              className="w-full"
                              placeholder="1000"
                              min={1}
                              precision={0}
                              addonAfter="ms"
                              disabled={disabledFormItems.multiline_timeout_ms}
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

export { useDockerVectorFormItems };
