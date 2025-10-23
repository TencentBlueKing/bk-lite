import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { M_TIMEOUT_UNITS } from '@/app/log/constants';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useConditionModeList } from '@/app/log/hooks/integration/common/other';
const { Option } = Select;
const { TextArea } = Input;

const useDockerVectorFormItems = () => {
  const { t } = useTranslation();
  const conditionModeList = useConditionModeList();

  return {
    getCommonFormItems: (
      extra: {
        disabledFormItems: Record<string, boolean>;
        hiddenFormItems: Record<string, boolean>;
      } = {
        disabledFormItems: {},
        hiddenFormItems: {},
      }
    ) => {
      return (
        <>
          <Form.Item
            label={t('log.integration.host')}
            required={true}
            name="docker_host"
            rules={[
              {
                required: true,
                message: t('common.required'),
              },
            ]}
          >
            <Input disabled={extra.disabledFormItems.docker_host} />
          </Form.Item>
          {!extra.hiddenFormItems.include_containers && (
            <Form.Item
              label={t('log.integration.includeContainers')}
              name="include_containers"
            >
              <Select
                mode="tags"
                placeholder={t('log.integration.containerPlaceholder')}
                disabled={extra.disabledFormItems.include_containers}
                suffixIcon={null}
                open={false}
              />
            </Form.Item>
          )}
          {!extra.hiddenFormItems.exclude_containers && (
            <Form.Item
              label={t('log.integration.excludeContainers')}
              name="exclude_containers"
            >
              <Select
                mode="tags"
                placeholder={t('log.integration.containerPlaceholder')}
                disabled={extra.disabledFormItems.exclude_containers}
                suffixIcon={null}
                open={false}
              />
            </Form.Item>
          )}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px]">
                {t('log.integration.multiline')}
              </span>
              <Form.Item noStyle name={['multiline', 'enabled']}>
                <Switch />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)]">
            {t('log.integration.multilineDes')}
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
                  className={`border rounded-md mt-[10px] px-[20px] pt-[20px] mb-[20px] ${
                    !multilineEnabled ? 'hidden' : ''
                  }`}
                >
                  {multilineEnabled && (
                    <Form.Item
                      name="multiline"
                      rules={[
                        ({ getFieldValue }) => ({
                          validator() {
                            const multiline = getFieldValue('multiline') || {};
                            const hasAny = Object.values(multiline).some(
                              (v) => v && v !== ''
                            );
                            const hasAll =
                              multiline.start_pattern &&
                              multiline.condition_pattern &&
                              multiline.mode &&
                              multiline.timeout_ms;

                            if (hasAny && !hasAll) {
                              return Promise.reject(
                                new Error(
                                  t('log.integration.multilineAllRequired')
                                )
                              );
                            }
                            return Promise.resolve();
                          },
                        }),
                      ]}
                    >
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.startPattern')}
                            />
                            <Tooltip
                              title={
                                <div style={{ whiteSpace: 'pre-line' }}>
                                  {t('log.integration.startPatternTips')}
                                </div>
                              }
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            name={['multiline', 'start_pattern']}
                            noStyle
                          >
                            <TextArea
                              placeholder={t('log.integration.startPattern')}
                              rows={2}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.conditionPattern')}
                            />
                            <Tooltip
                              title={
                                <div style={{ whiteSpace: 'pre-line' }}>
                                  {t('log.integration.conditionPatternTips')}
                                </div>
                              }
                            >
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item
                            name={['multiline', 'condition_pattern']}
                            noStyle
                          >
                            <TextArea
                              placeholder={t(
                                'log.integration.conditionPattern'
                              )}
                              rows={2}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.mode')}
                            />
                            <Tooltip title={t('log.integration.modeTips')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'mode']} noStyle>
                            <Select
                              placeholder={t('log.integration.mode')}
                              style={{ width: '100%' }}
                            >
                              {conditionModeList.map((item) => (
                                <Option key={item.value} value={item.value}>
                                  <Tooltip title={item.label}>
                                    {item.title}
                                  </Tooltip>
                                </Option>
                              ))}
                            </Select>
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-0" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.timeoutMs')}
                            />
                            <Tooltip title={t('log.integration.timeoutMsTips')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'timeout_ms']} noStyle>
                            <InputNumber
                              className="w-full"
                              placeholder={t('log.integration.timeoutMs')}
                              min={1}
                              precision={0}
                              addonAfter={
                                <Select
                                  style={{ width: 116 }}
                                  defaultValue="ms"
                                >
                                  {M_TIMEOUT_UNITS.map((item: string) => (
                                    <Option key={item} value={item}>
                                      {item}
                                    </Option>
                                  ))}
                                </Select>
                              }
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                    </Form.Item>
                  )}
                </div>
              );
            }}
          </Form.Item>
        </>
      );
    },
  };
};

export { useDockerVectorFormItems };
