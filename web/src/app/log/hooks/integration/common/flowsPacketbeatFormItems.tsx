import React from 'react';
import { Form, InputNumber, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { QuestionCircleOutlined } from '@ant-design/icons';

const useFlowsPacketbeatFormItems = () => {
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
          {/* 网络流抓取 - 标题 */}
          <div className="font-semibold mb-[8px]">
            {t('log.integration.flowsTrafficCapture')}
          </div>
          <div className="text-[var(--color-text-3)] mb-[12px]">
            {t('log.integration.flowsTrafficCaptureDesc')}
          </div>

          {/* 表单区块 */}
          <div className="bg-[var(--color-fill-1)] rounded-md px-[20px] py-[16px] mb-[20px]">
            {/* 统计周期 */}
            <Form.Item className="mb-[10px]">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.flowsStatisticsPeriod')}
                  </span>
                  <Tooltip
                    title={t('log.integration.flowsStatisticsPeriodHint')}
                  >
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="flows_period">
                  <InputNumber
                    className="w-full"
                    placeholder="10"
                    min={1}
                    precision={0}
                    addonAfter="s"
                    disabled={disabledFormItems.flows_period}
                  />
                </Form.Item>
              </div>
            </Form.Item>

            {/* 超时时间 */}
            <Form.Item className="mb-0">
              <div className="flex items-center">
                <div className="flex items-center w-[100px] shrink-0 mr-[10px]">
                  <span className="whitespace-nowrap">
                    {t('log.integration.flowsTimeoutLabel')}
                  </span>
                  <Tooltip title={t('log.integration.flowsTimeoutHint')}>
                    <QuestionCircleOutlined className="text-[var(--ant-color-text-description)] ml-[4px]" />
                  </Tooltip>
                </div>
                <Form.Item className="mb-0 flex-1" name="flows_timeout">
                  <InputNumber
                    className="w-full"
                    placeholder="30"
                    min={1}
                    precision={0}
                    addonAfter="s"
                    disabled={disabledFormItems.flows_timeout}
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

export { useFlowsPacketbeatFormItems };
