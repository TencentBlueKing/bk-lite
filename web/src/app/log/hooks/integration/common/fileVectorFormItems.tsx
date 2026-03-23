import React from 'react';
import { Form, Input, InputNumber, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useConditionModeList } from '@/app/log/hooks/integration/common/other';
const { Option } = Select;

const useFileVectorFormItems = () => {
  const { t } = useTranslation();
  const conditionModeList = useConditionModeList();

  // 编码选项
  const encodingOptions = [
    { value: 'utf-8', label: 'UTF-8' },
    { value: 'gbk', label: 'GBK' },
    { value: 'gb2312', label: 'GB2312' },
    { value: 'utf-16le', label: 'UTF-16LE' },
    { value: 'iso-8859-1', label: 'ISO-8859-1' }
  ];

  // 读取位置选项
  const readFromOptions = [
    { value: 'beginning', label: t('log.integration.fileReadFromBeginning') },
    { value: 'end', label: t('log.integration.fileReadFromEnd') }
  ];

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
          {/* 文件路径配置区块 */}
          <div className="font-semibold mb-[8px]">
            {t('log.integration.filePathConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.filePathConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            {/* 日志路径 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.filePaths')}
                  </span>
                  <Tooltip
                    title={
                      <div style={{ whiteSpace: 'pre-line' }}>
                        {t('log.integration.filePathsHint')}
                      </div>
                    }
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                  <span className="text-red-500 ml-[2px]">*</span>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name="include"
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <Select
                    mode="tags"
                    placeholder={t('log.integration.filePathsPlaceholder')}
                    disabled={disabledFormItems.include}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
            {/* 排除路径 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileExcludePaths')}
                  </span>
                  <Tooltip
                    title={
                      <div style={{ whiteSpace: 'pre-line' }}>
                        {t('log.integration.fileExcludePathsHint')}
                      </div>
                    }
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="exclude">
                  <Select
                    mode="tags"
                    placeholder={t(
                      'log.integration.fileExcludePathsPlaceholder'
                    )}
                    disabled={disabledFormItems.exclude}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
          </div>

          {/* parser_type - 隐藏字段，默认不解析 */}
          <Form.Item noStyle name="parser_type" initialValue="">
            <input type="hidden" />
          </Form.Item>

          {/* 多行合并配置 */}
          <Form.Item layout="vertical" className="mb-[8px]">
            <div className="flex items-center">
              <span className="mr-[10px] font-semibold">
                {t('log.integration.multiline')}
              </span>
              <Form.Item noStyle name={['multiline', 'enabled']}>
                <Switch disabled={disabledFormItems.multiline_enabled} />
              </Form.Item>
            </div>
          </Form.Item>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.fileMultilineDesc')}
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
                      {/* 合并模式 */}
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
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
                      {/* 匹配正则 */}
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
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
                      {/* 起始行正则 */}
                      <Form.Item className="mb-[10px]">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                            <span className="whitespace-nowrap">
                              {t('log.integration.startPattern')}
                            </span>
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
                            className="mb-0 flex-1"
                            name={['multiline', 'start_pattern']}
                          >
                            <Input
                              placeholder="^\d{4}-\d{2}-\d{2}"
                              disabled={
                                disabledFormItems.multiline_start_pattern
                              }
                            />
                          </Form.Item>
                        </div>
                      </Form.Item>
                      {/* 多行等待超时 */}
                      <Form.Item className="mb-0">
                        <div className="flex items-center">
                          <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
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

          {/* 高级配置区块 */}
          <div className="font-semibold mb-[8px]">
            {t('log.integration.fileAdvancedConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.fileAdvancedConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            {/* 读取位置 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileReadFrom')}
                  </span>
                  <Tooltip title={t('log.integration.fileReadFromHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="read_from">
                  <Select
                    placeholder={t('log.integration.fileReadFrom')}
                    disabled={disabledFormItems.read_from}
                  >
                    {readFromOptions.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </div>
            </Form.Item>
            {/* 文件编码 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileEncoding')}
                  </span>
                  <Tooltip title={t('log.integration.fileEncodingHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="encoding_charset">
                  <Select
                    placeholder={t('log.integration.fileEncoding')}
                    disabled={disabledFormItems.encoding_charset}
                  >
                    {encodingOptions.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </div>
            </Form.Item>
            {/* 忽略过旧文件 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileIgnoreOlderSecs')}
                  </span>
                  <Tooltip title={t('log.integration.fileIgnoreOlderSecsHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="ignore_older_secs">
                  <InputNumber
                    className="w-full"
                    placeholder="86400"
                    min={1}
                    precision={0}
                    addonAfter="s"
                    disabled={disabledFormItems.ignore_older_secs}
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

export { useFileVectorFormItems };
