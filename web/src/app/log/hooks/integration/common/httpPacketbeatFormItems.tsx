import React from 'react';
import { Form, Select, Switch, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const useHttpPacketbeatFormItems = () => {
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
          {/* HTTP 流量抓取 - 标题 */}
          <div className="font-semibold mb-[8px]">
            {t('log.integration.httpTrafficCapture')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.httpTrafficCaptureDesc')}
          </div>

          {/* 表单区块 */}
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            {/* 监听端口 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.httpListenPorts')}
                  </span>
                  <span className="text-red-500 ml-[2px]">*</span>
                  <Tooltip title={t('log.integration.httpListenPortsHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0 flex-1"
                  name="ports"
                  rules={[
                    {
                      required: true,
                      message: t('common.required')
                    }
                  ]}
                >
                  <Select
                    mode="tags"
                    placeholder={t('log.integration.httpPortsPlaceholder')}
                    disabled={disabledFormItems.ports}
                    suffixIcon={null}
                    open={false}
                  />
                </Form.Item>
              </div>
            </Form.Item>

            {/* 抓取请求体 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.httpCaptureBody')}
                  </span>
                  <Tooltip title={t('log.integration.httpCaptureBodyHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item
                  className="mb-0"
                  name="capture_body"
                  valuePropName="checked"
                >
                  <Switch disabled={disabledFormItems.capture_body} />
                </Form.Item>
              </div>
            </Form.Item>
          </div>
        </>
      );
    }
  };
};

export { useHttpPacketbeatFormItems };
