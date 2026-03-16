import React from 'react';
import { Form, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const { Option } = Select;

const useFileIntegrityAuditbeatFormItems = () => {
  const { t } = useTranslation();

  // 哈希算法选项
  const hashAlgorithmOptions = [
    { value: 'sha256', label: 'SHA256' },
    { value: 'sha1', label: 'SHA1' },
    { value: 'sha512', label: 'SHA512' },
    { value: 'md5', label: 'MD5' }
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
          {/* 监控路径配置区块 - 标题带*必填 */}
          <div className="font-semibold mb-[8px]">
            <span className="text-red-500 mr-[2px]">*</span>
            {t('log.integration.fileIntegrityPathConfig')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px] text-[12px]">
            {t('log.integration.fileIntegrityPathConfigDesc')}
          </div>
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            {/* 监控路径 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileIntegrityMonitorPaths')}
                  </span>
                  <Tooltip
                    title={t('log.integration.fileIntegrityMonitorPathsHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="monitor_paths">
                  <Select
                    mode="tags"
                    placeholder={t(
                      'log.integration.fileIntegrityMonitorPathsPlaceholder'
                    )}
                    disabled={disabledFormItems.monitor_paths}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
            {/* 排除路径 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileIntegrityExcludePaths')}
                  </span>
                  <Tooltip
                    title={t('log.integration.fileIntegrityExcludePathsHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="exclude_paths">
                  <Select
                    mode="tags"
                    placeholder={t(
                      'log.integration.fileIntegrityExcludePathsPlaceholder'
                    )}
                    disabled={disabledFormItems.exclude_paths}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>
            {/* 哈希算法 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileIntegrityHashAlgorithm')}
                  </span>
                  <Tooltip
                    title={t('log.integration.fileIntegrityHashAlgorithmHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="hash_algorithm">
                  <Select
                    placeholder={t(
                      'log.integration.fileIntegrityHashAlgorithm'
                    )}
                    disabled={disabledFormItems.hash_algorithm}
                  >
                    {hashAlgorithmOptions.map((item) => (
                      <Option key={item.value} value={item.value}>
                        {item.label}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </div>
            </Form.Item>
            {/* 递归监控 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.fileIntegrityRecursive')}
                  </span>
                  <Tooltip
                    title={t('log.integration.fileIntegrityRecursiveHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0"
                  name="recursive_monitor"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.recursive_monitor} />
                </Form.Item>
              </div>
            </Form.Item>
          </div>
        </>
      );
    }
  };
};

export { useFileIntegrityAuditbeatFormItems };
