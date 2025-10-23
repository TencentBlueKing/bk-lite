import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TIMEOUT_UNITS } from '@/app/log/constants';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useDirectionList } from '@/app/log/hooks/integration/common/other';
const { Option } = Select;
const { TextArea } = Input;

const useFilestreamFilebeatFormItems = () => {
  const { t } = useTranslation();
  const directionList = useDirectionList();

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
          {!extra.hiddenFormItems.paths && (
            <Form.Item
              name="paths"
              label={t('log.integration.paths')}
              required
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select
                mode="tags"
                placeholder={t('log.integration.paths')}
                disabled={extra.disabledFormItems.paths}
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
                              multiline.match &&
                              multiline.pattern &&
                              multiline.max_lines &&
                              multiline.timeout;

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
                              text={t('log.integration.pattern')}
                            />
                            <Tooltip title={t('log.integration.patternDes')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'pattern']} noStyle>
                            <TextArea
                              placeholder={t('log.integration.pattern')}
                              rows={2}
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.negate')}
                            />
                            <Tooltip title={t('log.integration.negateDes')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'negate']} noStyle>
                            <Switch />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.match')}
                            />
                            <Tooltip title={t('log.integration.matchDes')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'match']} noStyle>
                            <Select placeholder={t('log.integration.match')}>
                              {directionList.map((item) => (
                                <Option key={item.id} value={item.id}>
                                  {item.name}
                                </Option>
                              ))}
                            </Select>
                          </Form.Item>
                        </div>
                      </Form.Item>
                      <Form.Item className="mb-[10px]" layout="vertical">
                        <div className="flex items-center justify-between">
                          <div className="flex w-[100px] mr-[10px]">
                            <EllipsisWithTooltip
                              className="overflow-hidden text-ellipsis whitespace-nowrap"
                              text={t('log.integration.maxLines')}
                            />
                            <Tooltip title={t('log.integration.maxLinesDes')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'max_lines']} noStyle>
                            <InputNumber
                              className="w-full"
                              placeholder={t('log.integration.maxLines')}
                              min={1}
                              precision={0}
                            />
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
                            <Tooltip title={t('log.integration.timeoutDes')}>
                              <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                            </Tooltip>
                          </div>
                          <Form.Item name={['multiline', 'timeout']} noStyle>
                            <InputNumber
                              className="w-full"
                              placeholder={t('log.integration.timeoutMs')}
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

export { useFilestreamFilebeatFormItems };
